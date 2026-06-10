"""Data loading and optional free live-data adapters."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import math
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from .io_utils import read_csv_dicts, write_csv_dicts
from .schemas import PRICE_COLUMNS, UNIVERSE_COLUMNS


def parse_date(value: str | dt.date | dt.datetime) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def parse_float(value: object, default: float = math.nan) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int(value: object, default: int = 0) -> int:
    number = parse_float(value, math.nan)
    if math.isnan(number):
        return default
    return int(number)


def normalize_ticker(ticker: object) -> str:
    return str(ticker or "").strip().upper()


def load_prices_csv(path: str | Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in read_csv_dicts(path):
        ticker = normalize_ticker(row.get("ticker"))
        if not ticker:
            continue
        date = parse_date(str(row.get("date", "")))
        close = parse_float(row.get("close"))
        adj_close = parse_float(row.get("adj_close"), close)
        normalized = {
            "ticker": ticker,
            "date": date,
            "open": parse_float(row.get("open"), close),
            "high": parse_float(row.get("high"), close),
            "low": parse_float(row.get("low"), close),
            "close": close,
            "adj_close": adj_close,
            "volume": parse_int(row.get("volume"), 0),
            "source": row.get("source") or f"csv:{Path(path).name}",
            "fetched_at": row.get("fetched_at") or "fixture",
        }
        if not math.isnan(normalized["adj_close"]):
            rows.append(normalized)
    rows.sort(key=lambda r: (r["ticker"], r["date"]))
    return rows


def load_universe_csv(path: str | Path | None, tickers: Iterable[str] | None = None) -> list[dict[str, object]]:
    if path:
        rows = []
        for row in read_csv_dicts(path):
            ticker = normalize_ticker(row.get("ticker"))
            if not ticker:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "name": row.get("name") or ticker,
                    "exchange": row.get("exchange") or "UNKNOWN",
                    "asset_type": row.get("asset_type") or "stock",
                    "active": _parse_bool(row.get("active"), True),
                    "market_cap": parse_float(row.get("market_cap")),
                    "sector": row.get("sector") or "UNKNOWN",
                    "source": row.get("source") or f"csv:{Path(path).name}",
                    "as_of_date": row.get("as_of_date") or "unknown",
                }
            )
        rows.sort(key=lambda r: r["ticker"])
        return rows
    rows = []
    for ticker in sorted({normalize_ticker(t) for t in (tickers or []) if normalize_ticker(t)}):
        rows.append(
            {
                "ticker": ticker,
                "name": ticker,
                "exchange": "UNKNOWN",
                "asset_type": "stock",
                "active": True,
                "market_cap": math.nan,
                "sector": "UNKNOWN",
                "source": "inferred_from_prices",
                "as_of_date": "unknown",
            }
        )
    return rows


def load_fundamentals_csv(path: str | Path | None) -> dict[str, list[dict[str, object]]]:
    if not path:
        return {}
    fundamentals: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in read_csv_dicts(path):
        ticker = normalize_ticker(row.get("ticker"))
        if not ticker:
            continue
        available_raw = row.get("available_at")
        if not available_raw:
            # Static/current snapshots are not point-in-time and must not be used historically.
            fundamentals[ticker].append({"available_at": None, "as_of_date": None})
            continue
        record: dict[str, object] = {
            "as_of_date": parse_date(row.get("as_of_date") or available_raw),
            "available_at": parse_date(available_raw),
        }
        for key, value in row.items():
            if key in {"ticker", "as_of_date", "available_at"}:
                continue
            parsed = parse_float(value)
            if not math.isnan(parsed):
                record[key] = parsed
        fundamentals[ticker].append(record)
    for records in fundamentals.values():
        records.sort(key=lambda r: (r.get("available_at") or dt.date.min, r.get("as_of_date") or dt.date.min))
    return dict(fundamentals)


def group_prices(prices: Iterable[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in prices:
        grouped[str(row["ticker"])].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda r: r["date"])
    return dict(grouped)


def price_dates(prices: Iterable[dict[str, object]]) -> list[dt.date]:
    return sorted({row["date"] for row in prices if isinstance(row["date"], dt.date)})


def serialize_prices(prices: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in prices:
        out.append({**row, "date": row["date"].isoformat() if hasattr(row["date"], "isoformat") else row["date"]})
    return out


def serialize_universe(universe: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in universe:
        out.append({col: row.get(col, "") for col in UNIVERSE_COLUMNS})
    return out


def write_universe_snapshot(path: str | Path, universe: list[dict[str, object]]) -> None:
    write_csv_dicts(path, serialize_universe(universe), UNIVERSE_COLUMNS)


def fetch_yfinance_prices(tickers: list[str], period: str, cache_dir: str | Path | None = None) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Fetch prices through yfinance if the optional extra is installed."""
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency path
        raise RuntimeError("Install optional live dependency with `pip install -e .[live]` to use provider yfinance") from exc

    fetched_at = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    data = yf.download(tickers, period=period, auto_adjust=False, progress=False, group_by="ticker")
    rows: list[dict[str, object]] = []
    failed_tickers: list[str] = []
    succeeded_tickers: list[str] = []
    # yfinance returns pandas objects; keep import optional and access duck-typed.
    for ticker in tickers:
        ticker_row_count = 0
        try:
            table = data[ticker] if len(tickers) > 1 else data
        except Exception:
            failed_tickers.append(ticker)
            continue
        if getattr(table, "empty", False):
            failed_tickers.append(ticker)
            continue
        for idx, rec in table.iterrows():
            close = float(rec.get("Close", math.nan))
            adj = float(rec.get("Adj Close", close)) if "Adj Close" in rec else close
            if math.isnan(adj):
                continue
            rows.append(
                {
                    "ticker": normalize_ticker(ticker),
                    "date": parse_date(idx.date() if hasattr(idx, "date") else str(idx)[:10]),
                    "open": float(rec.get("Open", close)),
                    "high": float(rec.get("High", close)),
                    "low": float(rec.get("Low", close)),
                    "close": close,
                    "adj_close": adj,
                    "volume": int(float(rec.get("Volume", 0) or 0)),
                    "source": "yfinance",
                    "fetched_at": fetched_at,
                }
            )
            ticker_row_count += 1
        if ticker_row_count:
            succeeded_tickers.append(ticker)
        else:
            failed_tickers.append(ticker)
    rows.sort(key=lambda r: (r["ticker"], r["date"]))
    if cache_dir:
        cache_path = Path(cache_dir) / f"yfinance-{hashlib.sha256(' '.join(tickers).encode()).hexdigest()[:12]}.csv"
        write_csv_dicts(cache_path, serialize_prices(rows), PRICE_COLUMNS)
    metadata = {
        "provider": "yfinance",
        "provider_version": _package_version("yfinance"),
        "fetched_at": fetched_at,
        "source": "Yahoo Finance public APIs via yfinance",
        "cache_dir": str(cache_dir or ""),
        "requested_tickers": list(tickers),
        "succeeded_tickers": succeeded_tickers,
        "failed_tickers": failed_tickers,
    }
    return rows, metadata


def download_nasdaq_symbol_directory(url: str, output_path: str | Path) -> Path:
    """Download a Nasdaq Trader symbol directory text file for current-universe seeding."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=30) as response:  # nosec - user-requested public data URL helper
        output.write_bytes(response.read())
    return output


def source_hash_for_paths(paths: Iterable[str | Path | None]) -> str:
    h = hashlib.sha256()
    for path in paths:
        if not path:
            continue
        p = Path(path)
        if p.exists():
            h.update(p.name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _parse_bool(value: object, default: bool) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "active"}


def _package_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
