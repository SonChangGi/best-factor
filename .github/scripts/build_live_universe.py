"""Build a best-factor universe CSV from a committed ticker list and yfinance metadata.

This helper is intentionally best-effort. Missing yfinance metadata is written as
blank fields so the main CLI can either apply a market-cap filter when possible
or retry without that filter in the workflow.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import sys
from pathlib import Path
from typing import Any

FIELDNAMES = ["ticker", "name", "exchange", "asset_type", "active", "market_cap", "sector", "source", "as_of_date"]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("usage: build_live_universe.py TICKERS_TXT OUTPUT_CSV", file=sys.stderr)
        return 2
    tickers = read_tickers(Path(args[0]))
    rows = fetch_rows(tickers)
    output = Path(args[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} universe rows to {output}")
    return 0


def read_tickers(path: Path) -> list[str]:
    seen: set[str] = set()
    tickers: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        ticker = raw.split("#", 1)[0].strip().upper()
        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    if not tickers:
        raise ValueError(f"no tickers found in {path}")
    return tickers


def fetch_rows(tickers: list[str]) -> list[dict[str, object]]:
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:  # pragma: no cover - optional CI/live path
        raise RuntimeError("Install yfinance to build live universe metadata") from exc

    today = dt.date.today().isoformat()
    rows: list[dict[str, object]] = []
    for ticker in tickers:
        row = {
            "ticker": ticker,
            "name": ticker,
            "exchange": "UNKNOWN",
            "asset_type": "stock",
            "active": True,
            "market_cap": "",
            "sector": "UNKNOWN",
            "source": "yfinance_current_metadata_screen",
            "as_of_date": today,
        }
        try:
            instrument = yf.Ticker(ticker)
            fast = getattr(instrument, "fast_info", {}) or {}
            info = safe_info(instrument)
            market_cap = first_number(
                get_value(fast, "market_cap"),
                get_value(fast, "marketCap"),
                info.get("marketCap"),
            )
            if market_cap is not None:
                row["market_cap"] = int(market_cap)
            row["name"] = info.get("shortName") or info.get("longName") or ticker
            row["exchange"] = info.get("exchange") or info.get("fullExchangeName") or "UNKNOWN"
            row["sector"] = info.get("sector") or "UNKNOWN"
        except Exception as exc:  # pragma: no cover - network/provider variability
            row["source"] = f"yfinance_metadata_error:{type(exc).__name__}"
        rows.append(row)
    return rows


def safe_info(instrument: Any) -> dict[str, Any]:
    try:
        info = getattr(instrument, "info", {}) or {}
    except Exception:
        return {}
    return info if isinstance(info, dict) else {}


def get_value(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    try:
        return getattr(obj, key)
    except Exception:
        return None


def first_number(*values: Any) -> float | None:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number) and number > 0:
            return number
    return None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
