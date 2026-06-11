"""Build the live Best Factor stock universe from a committed priority list.

The committed ticker file is the reproducible priority list.  This helper
validates that list against the current Nasdaq Trader symbol directories and
emits only conservative listed common-stock rows for the live dashboard.

Important economic limitation: Nasdaq Trader directories are current-universe
files, not historical point-in-time constituent data.  The dashboard discloses
that survivor/current-screen limitation in run metadata and caveats.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Iterable

from best_factor.data import (
    NASDAQ_LISTED_URL,
    OTHER_LISTED_URL,
    SYMBOL_DIRECTORY_URLS,
    normalize_ticker,
    parse_nasdaq_symbol_directory,
)

FIELDNAMES = ["ticker", "name", "exchange", "asset_type", "active", "market_cap", "sector", "source", "as_of_date"]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    priority_tickers = read_tickers(args.tickers_txt)
    candidates, metadata = load_symbol_directory_candidates(args.symbol_directory_url)
    rows, selection = select_committed_common_stocks(priority_tickers, candidates)
    if len(rows) < args.min_symbols:
        missing = args.min_symbols - len(rows)
        invalid_preview = ",".join(selection["invalid_tickers"][:20])
        raise ValueError(
            f"validated common-stock universe has {len(rows)} rows, below --min-symbols {args.min_symbols} "
            f"(short by {missing}; invalid preview: {invalid_preview})"
        )
    output = Path(args.output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows([{key: row.get(key, "") for key in FIELDNAMES} for row in rows])
    universe_metadata = {
        **metadata,
        **selection,
        "committed_priority_ticker_count": len(priority_tickers),
        "selected_universe_ticker_count": len(rows),
        "min_validated_symbol_count": args.min_symbols,
        "generated_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
        "universe_construction_note": (
            "Current Nasdaq Trader symbol directories validate the committed dashboard priority list; "
            "only conservative common-stock rows are emitted. This is not historical point-in-time membership."
        ),
    }
    if args.metadata_json:
        metadata_path = Path(args.metadata_json)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(universe_metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {len(rows)} validated common-stock universe rows to {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a validated best-factor live universe CSV")
    parser.add_argument("tickers_txt", type=Path, help="committed priority ticker list")
    parser.add_argument("output_csv", type=Path, help="universe CSV output path")
    parser.add_argument("--metadata-json", type=Path, help="optional universe-construction metadata JSON")
    parser.add_argument("--min-symbols", type=int, default=500, help="minimum validated stock rows required")
    parser.add_argument(
        "--symbol-directory-url",
        action="append",
        default=[],
        help="override/add Nasdaq Trader symbol directory URL; defaults to nasdaqlisted and otherlisted",
    )
    return parser


def read_tickers(path: Path) -> list[str]:
    seen: set[str] = set()
    tickers: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        ticker = normalize_ticker(raw.split("#", 1)[0])
        if ticker and ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    if not tickers:
        raise ValueError(f"no tickers found in {path}")
    return tickers


def load_symbol_directory_candidates(urls: Iterable[str] | None = None) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    source_urls = list(urls or SYMBOL_DIRECTORY_URLS)
    by_ticker: dict[str, dict[str, object]] = {}
    source_metadata: list[dict[str, object]] = []
    combined_exclusions: Counter[str] = Counter()
    raw_payloads: list[bytes] = []
    for url in source_urls:
        payload = download_text(url)
        raw_payloads.append(payload.encode("utf-8"))
        rows, metadata = parse_nasdaq_symbol_directory(payload, source_url=url)
        source_metadata.append(metadata)
        combined_exclusions.update(metadata.get("excluded_symbol_counts", {}))
        for row in rows:
            ticker = str(row["ticker"])
            by_ticker.setdefault(ticker, row)
    metadata = {
        "universe_source_urls": source_urls,
        "symbol_directory_source_hash": hashlib.sha256(b"\n".join(raw_payloads)).hexdigest()[:16],
        "symbol_directory_sources": source_metadata,
        "raw_symbol_count": sum(int(item.get("raw_symbol_count", 0)) for item in source_metadata),
        "common_stock_candidate_count": len(by_ticker),
        "excluded_symbol_counts": dict(sorted(combined_exclusions.items())),
    }
    return by_ticker, metadata


def select_committed_common_stocks(
    priority_tickers: list[str],
    candidates_by_ticker: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    rows: list[dict[str, object]] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for ticker in priority_tickers:
        if ticker in seen:
            continue
        seen.add(ticker)
        candidate = candidates_by_ticker.get(ticker)
        if not candidate:
            invalid.append(ticker)
            continue
        rows.append({key: candidate.get(key, "") for key in FIELDNAMES})
    return rows, {
        "invalid_tickers": invalid,
        "invalid_ticker_count": len(invalid),
        "selected_tickers": [str(row["ticker"]) for row in rows],
    }


def download_text(url: str) -> str:
    if url not in {NASDAQ_LISTED_URL, OTHER_LISTED_URL}:
        # Reuse the package URL validation surface by allowing only Nasdaq Trader https hosts.
        from best_factor.data import download_nasdaq_symbol_directory
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = download_nasdaq_symbol_directory(url, Path(tmp) / "symbols.txt")
            return path.read_text(encoding="utf-8", errors="replace")
    with urllib.request.urlopen(url, timeout=30) as response:  # nosec - fixed public Nasdaq Trader URLs
        return response.read().decode("utf-8", errors="replace")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
