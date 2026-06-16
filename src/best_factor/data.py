"""Data loading and optional free live-data adapters."""
from __future__ import annotations

import datetime as dt
import csv
import hashlib
import importlib.metadata
import json
import math
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, urlencode, urlparse

from .io_utils import read_csv_dicts, write_csv_dicts
from .schemas import PRICE_COLUMNS, UNIVERSE_COLUMNS

ALLOWED_SYMBOL_DIRECTORY_HOSTS = {"www.nasdaqtrader.com", "nasdaqtrader.com"}
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"
SYMBOL_DIRECTORY_URLS = (NASDAQ_LISTED_URL, OTHER_LISTED_URL)
BENCHMARK_AND_FUND_TICKERS = {"^IXIC", "QQQ", "ONEQ", "SPY", "VOO", "VTI", "DIA", "IWM"}
YAHOO_CHART_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
YAHOO_CHART_USER_AGENT = "best-factor/1.0 (+https://sonchanggi.github.io/best-factor/)"
YAHOO_CHART_MAX_WORKERS = 8
YAHOO_CHART_PERIOD_RE = re.compile(r"^(?:\d+(?:d|wk|mo|y)|ytd|max)$", re.IGNORECASE)
_EXCLUDED_SECURITY_NAME_PATTERNS = {
    "etf": (" ETF", "EXCHANGE TRADED", "ETF -", " ETF"),
    "fund": (" FUND", "CLOSED-END", "MUTUAL FUND"),
    "etn_note_bond": (" ETN", "NOTE", "NOTES", "BOND", "DEBENTURE"),
    "preferred": ("PREFERRED", "PREFERENCE", "PREF ", "DEPOSITARY SHARES"),
    "unit": (" UNIT", "UNITS", "- UNIT"),
    "warrant": ("WARRANT", "WARRANTS"),
    "right": (" RIGHT", "RIGHTS"),
    "adr_ads": ("AMERICAN DEPOSITARY", " ADR", " ADS"),
    "ordinary_or_foreign_share": ("ORDINARY SHARE", "ORDINARY SHARES", "COMMON SHARES"),
    "spac_or_blank_check": ("ACQUISITION CORP", "ACQUISITION CORPORATION", "BLANK CHECK"),
    "convertible_or_certificate": ("CONVERTIBLE", "CERTIFICATE", "REDEEMABLE", "SUBORDINATED"),
}


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
        open_, high, low, close = adjusted_ohlc_to_adj_close(
            parse_float(row.get("open"), close),
            parse_float(row.get("high"), close),
            parse_float(row.get("low"), close),
            close,
            adj_close,
        )
        normalized = {
            "ticker": ticker,
            "date": date,
            "open": open_,
            "high": high,
            "low": low,
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


def fetch_yfinance_prices(
    tickers: list[str],
    period: str,
    cache_dir: str | Path | None = None,
    *,
    chunk_size: int = 100,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Fetch prices through yfinance if the optional extra is installed.

    Large live universes are downloaded in bounded chunks so one provider
    timeout does not make a 500+ stock run opaque.  Success/failure is reported
    per ticker and enforced by the CLI's ``--min-price-tickers`` gate.
    """
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency path
        raise RuntimeError("Install optional live dependency with `pip install -e .[live]` to use provider yfinance") from exc

    requested = _dedupe_preserve_order(normalize_ticker(ticker) for ticker in tickers)
    chunk_size = max(1, int(chunk_size or 100))
    fetched_at = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    rows: list[dict[str, object]] = []
    failed_tickers: list[str] = []
    succeeded_tickers: list[str] = []
    chunk_errors: list[dict[str, object]] = []

    for start in range(0, len(requested), chunk_size):
        chunk = requested[start : start + chunk_size]
        if not chunk:
            continue
        try:
            data = _retry_yfinance_call(
                lambda c=chunk: yf.download(c, period=period, auto_adjust=False, progress=False, group_by="ticker", threads=True),
                operation=f"price download chunk {start // chunk_size + 1}",
            )
        except Exception as exc:  # pragma: no cover - network/provider variability
            failed_tickers.extend(chunk)
            chunk_errors.append({"chunk_index": start // chunk_size, "tickers": chunk, "error": f"{type(exc).__name__}: {exc}"})
            continue
        for ticker in chunk:
            ticker_row_count = 0
            try:
                table = data[ticker] if len(chunk) > 1 else data
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
                open_, high, low, adjusted_close = adjusted_ohlc_to_adj_close(
                    float(rec.get("Open", close)),
                    float(rec.get("High", close)),
                    float(rec.get("Low", close)),
                    close,
                    adj,
                )
                rows.append(
                    {
                        "ticker": normalize_ticker(ticker),
                        "date": parse_date(idx.date() if hasattr(idx, "date") else str(idx)[:10]),
                        "open": open_,
                        "high": high,
                        "low": low,
                        "close": adjusted_close,
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
    succeeded_tickers = sorted(set(succeeded_tickers))
    failed_tickers = sorted(set(failed_tickers) - set(succeeded_tickers))
    if cache_dir:
        cache_path = Path(cache_dir) / f"yfinance-{hashlib.sha256(' '.join(requested).encode()).hexdigest()[:12]}.csv"
        write_csv_dicts(cache_path, serialize_prices(rows), PRICE_COLUMNS)
    metadata = {
        "provider": "yfinance",
        "provider_version": _package_version("yfinance"),
        "fetched_at": fetched_at,
        "source": "Yahoo Finance public APIs via yfinance",
        "cache_dir": str(cache_dir or ""),
        "requested_tickers": list(requested),
        "requested_ticker_count": len(requested),
        "succeeded_tickers": succeeded_tickers,
        "failed_tickers": failed_tickers,
        "failed_price_ticker_count": len(failed_tickers),
        "price_download_chunk_size": chunk_size,
        "price_download_chunk_count": math.ceil(len(requested) / chunk_size) if requested else 0,
        "price_download_chunk_errors": chunk_errors,
        "price_download_success_rate": (len(succeeded_tickers) / len(requested)) if requested else 0.0,
        "price_adjustment": "open_high_low_close_scaled_to_adj_close",
    }
    return rows, metadata


def fetch_yahoo_chart_prices(
    tickers: list[str],
    period: str,
    cache_dir: str | Path | None = None,
    *,
    chunk_size: int = 100,
    timeout: int = 30,
    max_workers: int = YAHOO_CHART_MAX_WORKERS,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Fetch daily adjusted OHLCV prices from Yahoo's chart JSON endpoint.

    This adapter intentionally uses only the Python standard library.  It gives
    the live workflow a second free retrieval path when the optional yfinance
    package, its pandas parsing path, or a chunked yfinance request fails.  The
    underlying data is still Yahoo-family public data, so CLI coverage gates
    remain the real safety mechanism.
    """
    requested = _dedupe_preserve_order(normalize_ticker(ticker) for ticker in tickers)
    yahoo_period = _normalize_yahoo_chart_period(period)
    fetched_at = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    rows: list[dict[str, object]] = []
    succeeded_tickers: list[str] = []
    failed_tickers: list[str] = []
    request_errors: list[dict[str, object]] = []

    def fetch_one(ticker: str) -> tuple[str, list[dict[str, object]]]:
        payload = _retry_provider_call(
            lambda: _download_yahoo_chart_payload(ticker, yahoo_period, timeout=timeout),
            provider="yahoo_chart",
            operation=f"price download {ticker}",
        )
        return ticker, _rows_from_yahoo_chart_payload(ticker, payload, fetched_at)

    iterator: list[tuple[str, list[dict[str, object]]]] = []
    workers = min(max(1, int(max_workers or 1)), max(1, len(requested)))
    if workers == 1:
        for ticker in requested:
            try:
                iterator.append(fetch_one(ticker))
            except Exception as exc:  # pragma: no cover - network/provider variability
                request_errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
                failed_tickers.append(ticker)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fetch_one, ticker): ticker for ticker in requested}
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    iterator.append(future.result())
                except Exception as exc:  # pragma: no cover - network/provider variability
                    request_errors.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})
                    failed_tickers.append(ticker)

    for ticker, ticker_rows in iterator:
        if ticker_rows:
            rows.extend(ticker_rows)
            succeeded_tickers.append(ticker)
        else:
            failed_tickers.append(ticker)

    rows.sort(key=lambda r: (r["ticker"], r["date"]))
    succeeded_tickers = sorted(set(succeeded_tickers))
    failed_tickers = sorted(set(failed_tickers) - set(succeeded_tickers))
    if cache_dir:
        cache_path = Path(cache_dir) / f"yahoo-chart-{hashlib.sha256(' '.join(requested).encode()).hexdigest()[:12]}.csv"
        write_csv_dicts(cache_path, serialize_prices(rows), PRICE_COLUMNS)
    metadata = {
        "provider": "yahoo_chart",
        "provider_version": "direct-json-v8",
        "fetched_at": fetched_at,
        "source": "Yahoo Finance chart JSON endpoint via urllib",
        "cache_dir": str(cache_dir or ""),
        "requested_tickers": list(requested),
        "requested_ticker_count": len(requested),
        "succeeded_tickers": succeeded_tickers,
        "failed_tickers": failed_tickers,
        "failed_price_ticker_count": len(failed_tickers),
        "price_download_chunk_size": 1,
        "price_download_chunk_count": len(requested),
        "price_download_request_count": len(requested),
        "price_download_chunk_errors": request_errors,
        "price_download_success_rate": (len(succeeded_tickers) / len(requested)) if requested else 0.0,
        "price_adjustment": "open_high_low_close_scaled_to_adj_close",
        "provider_order": ["yahoo_chart"],
        "provider_attempted_sources": ["yahoo_chart"] if requested else [],
        "provider_fill_counts": {"yahoo_chart": len(succeeded_tickers)},
        "provider_failed_tickers_by_source": {"yahoo_chart": failed_tickers},
        "provider_error_count": len(request_errors),
        "provider_limitations": (
            "Direct Yahoo chart JSON is a free public endpoint and can be delayed, changed, "
            "rate-limited, or unavailable; it is not a licensed institutional feed."
        ),
    }
    return rows, metadata


def fetch_resilient_prices(
    tickers: list[str],
    period: str,
    cache_dir: str | Path | None = None,
    *,
    chunk_size: int = 100,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Fetch prices with yfinance first, then fill missing tickers via Yahoo chart JSON."""
    requested = _dedupe_preserve_order(normalize_ticker(ticker) for ticker in tickers)
    fetched_at = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    provider_errors: list[dict[str, object]] = []
    attempted_sources: list[str] = []
    primary_rows: list[dict[str, object]] = []
    primary_metadata: dict[str, object] = {}

    try:
        attempted_sources.append("yfinance")
        primary_rows, primary_metadata = fetch_yfinance_prices(requested, period, cache_dir, chunk_size=chunk_size)
    except Exception as exc:  # pragma: no cover - optional dependency/network path
        provider_errors.append({"provider": "yfinance", "error": f"{type(exc).__name__}: {exc}"})
        primary_metadata = {
            "provider": "yfinance",
            "provider_version": _package_version("yfinance"),
            "succeeded_tickers": [],
            "failed_tickers": list(requested),
            "failed_price_ticker_count": len(requested),
            "price_download_chunk_errors": provider_errors[-1:],
        }

    primary_success = set(_metadata_tickers(primary_metadata, "succeeded_tickers") or _tickers_from_price_rows(primary_rows))
    primary_failed = _metadata_tickers(primary_metadata, "failed_tickers")
    missing = [ticker for ticker in requested if ticker not in primary_success]
    fallback_rows: list[dict[str, object]] = []
    fallback_metadata: dict[str, object] = {}
    fallback_success: set[str] = set()
    fallback_failed: list[str] = []

    if missing:
        attempted_sources.append("yahoo_chart")
        try:
            fallback_rows, fallback_metadata = fetch_yahoo_chart_prices(
                missing,
                period,
                cache_dir,
                chunk_size=chunk_size,
            )
            fallback_success = set(_metadata_tickers(fallback_metadata, "succeeded_tickers") or _tickers_from_price_rows(fallback_rows))
            fallback_failed = _metadata_tickers(fallback_metadata, "failed_tickers")
        except Exception as exc:  # pragma: no cover - network/provider variability
            provider_errors.append({"provider": "yahoo_chart", "error": f"{type(exc).__name__}: {exc}"})
            fallback_metadata = {
                "provider": "yahoo_chart",
                "provider_version": "direct-json-v8",
                "succeeded_tickers": [],
                "failed_tickers": list(missing),
                "failed_price_ticker_count": len(missing),
                "price_download_chunk_errors": provider_errors[-1:],
            }
            fallback_failed = list(missing)

    rows = _merge_price_rows_prefer_first(primary_rows, fallback_rows)
    succeeded_tickers = sorted(_tickers_from_price_rows(rows))
    failed_tickers = sorted(set(requested) - set(succeeded_tickers))
    combined_errors = list(primary_metadata.get("price_download_chunk_errors") or []) + list(
        fallback_metadata.get("price_download_chunk_errors") or []
    )
    # Explicit provider_errors capture whole-provider exceptions; chunk/request
    # errors capture partial provider failures.  De-duplicate by representation.
    seen_errors: set[str] = set()
    all_errors: list[dict[str, object]] = []
    for item in [*provider_errors, *combined_errors]:
        key = repr(item)
        if key not in seen_errors:
            seen_errors.add(key)
            all_errors.append(item)

    primary_chunk_count = int(primary_metadata.get("price_download_chunk_count") or (math.ceil(len(requested) / max(1, int(chunk_size or 100))) if requested else 0))
    fallback_request_count = int(fallback_metadata.get("price_download_request_count") or (len(missing) if missing else 0))
    if cache_dir:
        cache_path = Path(cache_dir) / f"yfinance-yahoo-chart-{hashlib.sha256(' '.join(requested).encode()).hexdigest()[:12]}.csv"
        write_csv_dicts(cache_path, serialize_prices(rows), PRICE_COLUMNS)

    metadata = {
        "provider": "yfinance_yahoo_chart",
        "provider_version": f"yfinance:{_package_version('yfinance')}; yahoo_chart:direct-json-v8",
        "fetched_at": str(primary_metadata.get("fetched_at") or fetched_at),
        "source": "Yahoo Finance public APIs via yfinance primary plus direct Yahoo chart JSON fallback",
        "cache_dir": str(cache_dir or ""),
        "requested_tickers": list(requested),
        "requested_ticker_count": len(requested),
        "succeeded_tickers": succeeded_tickers,
        "failed_tickers": failed_tickers,
        "failed_price_ticker_count": len(failed_tickers),
        "price_download_chunk_size": max(1, int(chunk_size or 100)),
        "price_download_chunk_count": primary_chunk_count + fallback_request_count,
        "price_download_yfinance_chunk_count": primary_chunk_count,
        "price_download_yahoo_chart_request_count": fallback_request_count,
        "price_download_chunk_errors": all_errors,
        "price_download_success_rate": (len(succeeded_tickers) / len(requested)) if requested else 0.0,
        "price_adjustment": "open_high_low_close_scaled_to_adj_close",
        "provider_order": ["yfinance", "yahoo_chart"],
        "provider_attempted_sources": attempted_sources,
        "provider_fill_counts": {"yfinance": len(primary_success), "yahoo_chart": len(fallback_success)},
        "provider_failed_tickers_by_source": {"yfinance": primary_failed, "yahoo_chart": fallback_failed},
        "provider_error_count": len(all_errors),
        "fallback_source": "yahoo_chart",
        "fallback_filled_ticker_count": len(fallback_success),
        "fallback_filled_tickers": sorted(fallback_success),
        "provider_limitations": (
            "Both yfinance and direct Yahoo chart JSON are free Yahoo-family sources, not independent "
            "licensed feeds; fallback improves adapter/path resilience but does not remove Yahoo availability, "
            "revision, delay, rate-limit, or terms risks."
        ),
    }
    return rows, metadata


def download_nasdaq_symbol_directory(url: str, output_path: str | Path) -> Path:
    """Download a Nasdaq Trader symbol directory text file for current-universe seeding."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in ALLOWED_SYMBOL_DIRECTORY_HOSTS:
        raise ValueError("symbol directory URL must be HTTPS on nasdaqtrader.com")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=30) as response:  # nosec - restricted public Nasdaq Trader host
        output.write_bytes(response.read())
    return output


def parse_nasdaq_symbol_directory(text: str, *, source_url: str) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Parse and conservatively screen a Nasdaq Trader symbol directory file.

    The output is a current-universe candidate list, not a historical/PIT
    constituent set.  The filter intentionally prefers listed common-stock
    names and excludes ETF/fund/preferred/unit/warrant/right/ADR-style rows.
    """
    directory_rows, file_creation_time = _symbol_directory_rows(text)
    accepted: list[dict[str, object]] = []
    exclusions: Counter[str] = Counter()
    for row in directory_rows:
        ticker = normalize_ticker(row.get("Symbol") or row.get("ACT Symbol"))
        reason = symbol_directory_exclusion_reason(row)
        if reason:
            exclusions[reason] += 1
            continue
        accepted.append(
            {
                "ticker": ticker,
                "name": (row.get("Security Name") or ticker).strip(),
                "exchange": (row.get("Exchange") or row.get("Market Category") or "UNKNOWN").strip() or "UNKNOWN",
                "asset_type": "stock",
                "active": True,
                "market_cap": math.nan,
                "sector": "UNKNOWN",
                "source": "nasdaq_trader_symbol_directory_current_screen",
                "as_of_date": file_creation_time or dt.date.today().isoformat(),
                "security_name": (row.get("Security Name") or "").strip(),
                "symbol_directory_url": source_url,
            }
        )
    metadata = {
        "source_url": source_url,
        "file_creation_time": file_creation_time,
        "raw_symbol_count": len(directory_rows),
        "common_stock_candidate_count": len(accepted),
        "excluded_symbol_counts": dict(sorted(exclusions.items())),
    }
    return accepted, metadata


def symbol_directory_exclusion_reason(row: dict[str, str]) -> str:
    ticker = normalize_ticker(row.get("Symbol") or row.get("ACT Symbol"))
    name = str(row.get("Security Name") or "").upper()
    if not ticker or ticker in BENCHMARK_AND_FUND_TICKERS:
        return "benchmark_or_blank"
    if not re.fullmatch(r"[A-Z]{1,5}", ticker):
        return "unsupported_symbol_format"
    if str(row.get("ETF") or "").strip().upper() == "Y":
        return "etf"
    if str(row.get("Test Issue") or "").strip().upper() == "Y":
        return "test_issue"
    financial_status = str(row.get("Financial Status") or "N").strip().upper()
    if financial_status not in {"", "N"}:
        return "non_normal_financial_status"
    if str(row.get("NextShares") or "N").strip().upper() == "Y":
        return "nextshares"
    for reason, patterns in _EXCLUDED_SECURITY_NAME_PATTERNS.items():
        if any(pattern in f" {name} " for pattern in patterns):
            return reason
    if "COMMON STOCK" not in name:
        return "not_common_stock_name"
    return ""


def _symbol_directory_rows(text: str) -> tuple[list[dict[str, str]], str]:
    lines = [line for line in text.splitlines() if line.strip()]
    file_creation_time = ""
    data_lines: list[str] = []
    for line in lines:
        if line.startswith("File Creation Time"):
            parts = line.split(":", 1)
            file_creation_time = parts[1].strip() if len(parts) == 2 else line.strip()
            continue
        data_lines.append(line)
    if not data_lines:
        return [], file_creation_time
    reader = csv.DictReader(data_lines, delimiter="|")
    rows = [dict(row) for row in reader if row and not str(row.get(reader.fieldnames[0] if reader.fieldnames else "") or "").startswith("File Creation Time")]
    return rows, file_creation_time


def adjusted_ohlc_to_adj_close(open_: float, high: float, low: float, close: float, adj_close: float) -> tuple[float, float, float, float]:
    """Return OHLC values on the same adjusted scale as ``adj_close``.

    Yahoo-style data commonly supplies raw OHLC and an adjusted close.  Mixing
    raw high/low/open values with adjusted-close return factors makes range,
    breakout, overnight, and intraday signals internally inconsistent around
    dividends and splits.  The project stores one OHLC set, so normalize it to
    the total-return adjusted-close scale used by the backtest.
    """
    if not math.isfinite(adj_close):
        return open_, high, low, close
    if not math.isfinite(close) or close <= 0:
        close = adj_close
    ratio = adj_close / close if close > 0 and math.isfinite(close) else 1.0
    if not math.isfinite(ratio) or ratio <= 0:
        ratio = 1.0

    def scale(value: float, fallback: float) -> float:
        base = value if math.isfinite(value) else fallback
        if not math.isfinite(base):
            base = close
        adjusted = base * ratio
        return adjusted if math.isfinite(adjusted) else adj_close

    adjusted_open = scale(open_, close)
    adjusted_high = scale(high, max(open_, close) if math.isfinite(open_) else close)
    adjusted_low = scale(low, min(open_, close) if math.isfinite(open_) else close)
    if adjusted_high < adjusted_low:
        adjusted_high, adjusted_low = adjusted_low, adjusted_high
    return adjusted_open, adjusted_high, adjusted_low, adj_close


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


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _normalize_yahoo_chart_period(period: str) -> str:
    value = str(period or "").strip().lower()
    if not YAHOO_CHART_PERIOD_RE.fullmatch(value):
        raise ValueError(
            f"unsupported yahoo_chart period {period!r}; use Yahoo chart ranges such as 1mo, 4mo, 1y, 5y, ytd, or max"
        )
    return value


def _download_yahoo_chart_payload(ticker: str, period: str, *, timeout: int) -> dict[str, object]:
    symbol = quote(_yahoo_chart_symbol(ticker), safe="")
    query = urlencode(
        {
            "range": period,
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    request = urllib.request.Request(
        f"{YAHOO_CHART_BASE_URL}/{symbol}?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": YAHOO_CHART_USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec - fixed HTTPS Yahoo chart host
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Yahoo chart response was not a JSON object for {ticker}")
    return payload


def _rows_from_yahoo_chart_payload(ticker: str, payload: dict[str, object], fetched_at: str) -> list[dict[str, object]]:
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise ValueError(f"Yahoo chart response missing chart object for {ticker}")
    error = chart.get("error")
    if error:
        raise RuntimeError(f"Yahoo chart error for {ticker}: {error}")
    results = chart.get("result")
    if not isinstance(results, list) or not results:
        return []
    result = results[0]
    if not isinstance(result, dict):
        return []
    timestamps = result.get("timestamp")
    indicators = result.get("indicators")
    if not isinstance(timestamps, list) or not isinstance(indicators, dict):
        return []
    quotes = indicators.get("quote")
    quote_row = quotes[0] if isinstance(quotes, list) and quotes else {}
    if not isinstance(quote_row, dict):
        return []
    adj_rows = indicators.get("adjclose")
    adj_row = adj_rows[0] if isinstance(adj_rows, list) and adj_rows else {}
    if not isinstance(adj_row, dict):
        adj_row = {}
    opens = quote_row.get("open") if isinstance(quote_row.get("open"), list) else []
    highs = quote_row.get("high") if isinstance(quote_row.get("high"), list) else []
    lows = quote_row.get("low") if isinstance(quote_row.get("low"), list) else []
    closes = quote_row.get("close") if isinstance(quote_row.get("close"), list) else []
    volumes = quote_row.get("volume") if isinstance(quote_row.get("volume"), list) else []
    adjusted = adj_row.get("adjclose") if isinstance(adj_row.get("adjclose"), list) else []

    rows: list[dict[str, object]] = []
    normalized = normalize_ticker(ticker)
    for idx, timestamp in enumerate(timestamps):
        close = _series_float(closes, idx)
        adj_close = _series_float(adjusted, idx, default=close)
        if not math.isfinite(close) and math.isfinite(adj_close):
            close = adj_close
        if not math.isfinite(adj_close):
            continue
        open_, high, low, adjusted_close = adjusted_ohlc_to_adj_close(
            _series_float(opens, idx, default=close),
            _series_float(highs, idx, default=close),
            _series_float(lows, idx, default=close),
            close,
            adj_close,
        )
        try:
            date_value = dt.datetime.fromtimestamp(int(timestamp), tz=dt.UTC).date()
        except (TypeError, ValueError, OSError):
            continue
        rows.append(
            {
                "ticker": normalized,
                "date": date_value,
                "open": open_,
                "high": high,
                "low": low,
                "close": adjusted_close,
                "adj_close": adj_close,
                "volume": max(0, parse_int(_series_value(volumes, idx), 0)),
                "source": "yahoo_chart",
                "fetched_at": fetched_at,
            }
        )
    return rows


def _series_value(values: object, idx: int) -> object:
    if isinstance(values, list) and 0 <= idx < len(values):
        return values[idx]
    return None


def _series_float(values: object, idx: int, default: float = math.nan) -> float:
    return parse_float(_series_value(values, idx), default)


def _yahoo_chart_symbol(ticker: str) -> str:
    return normalize_ticker(ticker).replace(".", "-")


def _metadata_tickers(metadata: dict[str, object], key: str) -> list[str]:
    values = metadata.get(key)
    if not isinstance(values, list):
        return []
    return sorted({normalize_ticker(value) for value in values if normalize_ticker(value)})


def _tickers_from_price_rows(rows: Iterable[dict[str, object]]) -> set[str]:
    return {normalize_ticker(row.get("ticker")) for row in rows if normalize_ticker(row.get("ticker"))}


def _merge_price_rows_prefer_first(
    primary_rows: Iterable[dict[str, object]],
    fallback_rows: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    seen: set[tuple[str, object]] = set()
    out: list[dict[str, object]] = []
    for row in [*primary_rows, *fallback_rows]:
        key = (normalize_ticker(row.get("ticker")), row.get("date"))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        out.append(row)
    out.sort(key=lambda r: (r["ticker"], r["date"]))
    return out


def _retry_provider_call(
    call,
    *,
    provider: str,
    operation: str,
    attempts: int = 3,
    initial_delay: float = 1.0,
):
    """Run a provider call with bounded retry/backoff for transient failures."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as exc:  # pragma: no cover - network/provider variability
            last_exc = exc
            if attempt >= attempts:
                break
            time.sleep(initial_delay * (2 ** (attempt - 1)))
    raise RuntimeError(f"{provider} {operation} failed after {attempts} attempts") from last_exc


def _retry_yfinance_call(call, operation: str, attempts: int = 3, initial_delay: float = 1.0):
    """Run a yfinance call with bounded retry/backoff for transient provider failures."""
    return _retry_provider_call(
        call,
        provider="yfinance",
        operation=operation,
        attempts=attempts,
        initial_delay=initial_delay,
    )
