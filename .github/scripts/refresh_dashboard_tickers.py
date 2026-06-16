"""Refresh the committed Best Factor dashboard ticker priority list.

This is an operator utility, not a scheduled workflow step.  It rebuilds the
priority list from current Nasdaq Trader common-stock candidates and ranks names
by recent free Yahoo-family average dollar volume so the public dashboard can broaden its
universe without admitting ETFs, benchmarks, ADRs, warrants, funds, or other
non-common-stock rows.

Economic limitation: both the symbol directories and Yahoo-family volume data
are current/free-data inputs, not historical point-in-time membership or
liquidity screens.  The dashboard and run metadata disclose that limitation.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from best_factor.data import fetch_resilient_prices

import build_live_universe

HEADER = [
    "# Best Factor live dashboard stock universe",
    "# Generated from Nasdaq Trader Symbol Directory conservative common-stock screen plus yfinance-primary/Yahoo-chart-fallback 4-month average dollar volume ranking.",
    "# Target: top {target_count:,} validated individual stocks by recent average dollar volume, expanding coverage beyond the prior 1,200-name universe.",
    "# Filters: ETF=N, Test Issue=N, Financial Status=N, letters-only tickers, Common Stock names only, no funds/units/warrants/rights/preferred/depositary/ADR/ordinary/common-share/SPAC-like names.",
    "# Benchmarks such as ^IXIC/ONEQ/QQQ are intentionally excluded and passed separately as benchmark-tickers.",
]
CONSOLE_SUMMARY_KEYS = [
    "candidate_count",
    "priced_ticker_count",
    "ranked_ticker_count",
    "selected_ticker_count",
    "top_tickers",
]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    candidates, symbol_metadata = build_live_universe.load_symbol_directory_candidates(args.symbol_directory_url)
    candidate_tickers = sorted(candidates)
    prices, provider_metadata = fetch_resilient_prices(
        candidate_tickers,
        args.period,
        args.cache_dir,
        chunk_size=args.price_chunk_size,
    )
    ranked = rank_by_average_dollar_volume(prices, min_observations=args.min_observations, window=args.adv_window)
    if len(ranked) < args.target_count:
        raise ValueError(
            f"only {len(ranked)} tickers had enough free Yahoo-family price/volume observations "
            f"for target {args.target_count}"
        )
    selected = [ticker for _, ticker, _ in ranked[: args.target_count]]
    write_tickers(args.output, selected, args.target_count)
    priced_tickers = {str(row.get("ticker") or "").upper() for row in prices if row.get("ticker")}
    summary = {
        "candidate_count": len(candidate_tickers),
        "price_row_count": len(prices),
        "priced_ticker_count": len(priced_tickers),
        "ranked_ticker_count": len(ranked),
        "selected_ticker_count": len(selected),
        "target_count": args.target_count,
        "period": args.period,
        "adv_window": args.adv_window,
        "min_observations": args.min_observations,
        "top_tickers": selected[:20],
        "symbol_metadata": symbol_metadata,
        "provider_metadata": provider_metadata,
    }
    if args.metadata_json:
        args.metadata_json.parent.mkdir(parents=True, exist_ok=True)
        args.metadata_json.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
    print(
        json.dumps(
            {key: summary[key] for key in CONSOLE_SUMMARY_KEYS},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh the Best Factor dashboard ticker priority list")
    parser.add_argument("--output", type=Path, default=Path(".github/best-factor-dashboard-tickers.txt"))
    parser.add_argument("--metadata-json", type=Path, help="optional JSON summary path")
    parser.add_argument("--target-count", type=int, default=1800)
    parser.add_argument("--period", default="4mo", help="Yahoo-family history period for recent liquidity ranking")
    parser.add_argument("--adv-window", type=int, default=84, help="max trailing rows used for average dollar volume")
    parser.add_argument("--min-observations", type=int, default=20, help="minimum valid price-volume observations required for ranking")
    parser.add_argument("--price-chunk-size", type=int, default=100)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/best-factor/universe-refresh"))
    parser.add_argument(
        "--symbol-directory-url",
        action="append",
        default=[],
        help="override/add Nasdaq Trader symbol directory URL; defaults to nasdaqlisted and otherlisted",
    )
    return parser


def rank_by_average_dollar_volume(
    prices: list[dict[str, object]],
    *,
    min_observations: int,
    window: int,
) -> list[tuple[float, str, int]]:
    by_ticker: dict[str, list[dict[str, object]]] = {}
    for row in prices:
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            by_ticker.setdefault(ticker, []).append(row)
    ranked: list[tuple[float, str, int]] = []
    for ticker, rows in by_ticker.items():
        values: list[float] = []
        for row in sorted(rows, key=lambda item: item.get("date"))[-max(1, window) :]:
            try:
                dollar_volume = float(row.get("adj_close") or 0.0) * float(row.get("volume") or 0.0)
            except (TypeError, ValueError):
                continue
            if math.isfinite(dollar_volume) and dollar_volume > 0:
                values.append(dollar_volume)
        if len(values) >= min_observations:
            ranked.append((sum(values) / len(values), ticker, len(values)))
    ranked.sort(key=lambda item: (item[0], item[2], item[1]), reverse=True)
    return ranked


def write_tickers(path: Path, tickers: list[str], target_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [line.format(target_count=target_count) for line in HEADER]
    lines.extend(tickers)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
