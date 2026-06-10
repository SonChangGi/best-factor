"""Command line interface for best-factor."""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections import Counter
from pathlib import Path

from .calendar import rebalance_dates as build_rebalance_dates
from .data import (
    fetch_yfinance_prices,
    load_fundamentals_csv,
    load_prices_csv,
    load_universe_csv,
    price_dates,
    source_hash_for_paths,
    write_universe_snapshot,
)
from .factors import DEFAULT_FACTORS, compute_factor_scores, serialize_factor_scores, validate_factor_names
from .io_utils import ensure_dir, write_csv_dicts, write_json
from .metrics import compute_metrics
from .portfolio import latest_holdings_for_best, run_backtests, serialize_holdings, serialize_returns
from .ranking import rank_factors
from .report import write_html_report, write_report
from .site import write_site_payload
from .schemas import (
    CAVEATS,
    FACTOR_SCORE_COLUMNS,
    HOLDING_COLUMNS,
    METRIC_COLUMNS,
    PORTFOLIO_RETURN_COLUMNS,
    PRICE_COLUMNS,
    RANKING_COLUMNS,
    TIMING_CONVENTION,
)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            run(args)
            return 0
        if args.command == "site":
            build_site(args)
            return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="best-factor", description="Rank US equity factors and emit latest holdings/weights.")
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="run a factor backtest")
    run.add_argument("--provider", choices=["csv", "yfinance"], default="csv")
    run.add_argument("--prices-file", help="long-form CSV prices file for provider=csv")
    run.add_argument("--universe-file", help="optional universe metadata CSV")
    run.add_argument("--fundamentals-file", help="optional fundamentals CSV")
    run.add_argument("--output-dir", required=True, help="directory for output artifacts")
    run.add_argument("--rebalance", choices=["M", "W"], default="M", help="M=monthly, W=weekly")
    run.add_argument("--top-n", type=int, default=10)
    run.add_argument("--weighting", choices=["equal", "score"], default="equal")
    run.add_argument("--min-market-cap", type=float, default=0.0)
    run.add_argument("--min-dollar-volume", type=float, default=0.0)
    run.add_argument("--transaction-cost-bps", type=float, default=0.0)
    run.add_argument("--tickers", nargs="*", default=[])
    run.add_argument("--period", default="5y")
    run.add_argument("--cache-dir", default=".cache/best-factor")
    run.add_argument("--factors", nargs="+", default=[f.name for f in DEFAULT_FACTORS])

    site = sub.add_parser("site", help="export run artifacts to GitHub Pages dashboard JSON")
    site.add_argument("--run-dir", required=True, help="directory containing best-factor run artifacts")
    site.add_argument("--output-file", required=True, help="JSON file to write, e.g. docs/data/latest-results.json")
    site.add_argument("--data-scope", default="csv_run", help="label shown in the dashboard, e.g. csv_run or live_free_data")
    return parser


def build_site(args: argparse.Namespace) -> dict[str, object]:
    return write_site_payload(args.run_dir, args.output_file, data_scope=args.data_scope)


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.top_n <= 0:
        raise ValueError("--top-n must be positive")
    requested_factors = validate_factor_names(args.factors)
    output_dir = ensure_dir(args.output_dir)
    cache_dir = ensure_dir(args.cache_dir)
    provider_metadata: dict[str, object]
    if args.provider == "csv":
        if not args.prices_file:
            raise ValueError("--prices-file is required when --provider csv")
        price_path = Path(args.prices_file)
        if not price_path.exists():
            raise FileNotFoundError(f"prices file not found: {price_path}")
        prices = load_prices_csv(price_path)
        provider_metadata = {
            "provider": "csv",
            "provider_version": "stdlib",
            "fetched_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
            "source": f"csv:{price_path}",
            "cache_dir": str(cache_dir),
        }
    else:
        tickers = [t.upper() for t in args.tickers]
        if not tickers:
            raise ValueError("--tickers are required when --provider yfinance")
        prices, provider_metadata = fetch_yfinance_prices(tickers, args.period, cache_dir)
    if not prices:
        raise ValueError("no prices loaded")
    tickers = sorted({str(row["ticker"]) for row in prices})
    universe = load_universe_csv(args.universe_file, tickers)
    fundamentals = load_fundamentals_csv(args.fundamentals_file)
    dates = price_dates(prices)
    schedule = build_rebalance_dates(dates, args.rebalance)
    if len(schedule) < 2:
        raise ValueError("not enough price history to form at least two rebalance dates")

    scores = compute_factor_scores(prices, schedule[:-1], fundamentals, requested_factors, requested_factors)
    backtest = run_backtests(
        prices,
        universe,
        scores,
        schedule,
        args.top_n,
        args.weighting,
        args.min_market_cap,
        args.min_dollar_volume,
        args.transaction_cost_bps,
    )
    returns = list(backtest["returns"])
    holdings = list(backtest["holdings"])
    skipped_reasons = dict(backtest["skipped_reasons"])
    metrics = compute_metrics(returns, args.rebalance)
    skipped_zero_coverage = {str(row["factor"]): "zero_coverage" for row in metrics if float(row.get("coverage", 0.0)) <= 0}
    rankable_metrics = [row for row in metrics if float(row.get("coverage", 0.0)) > 0]
    rankings = rank_factors(rankable_metrics)
    if not rankings:
        raise ValueError("no factor produced holdings after filters; nothing is rank-eligible")
    best_factor = str(rankings[0]["factor"])
    latest = latest_holdings_for_best(holdings, best_factor) if best_factor else []

    if skipped_zero_coverage:
        for factor in skipped_zero_coverage:
            skipped_reasons[f"zero_coverage:{factor}"] = skipped_reasons.get(f"zero_coverage:{factor}", 0) + 1
    tested_factor_count = len(set(requested_factors))
    effective_factor_count = len({r["factor"] for r in returns if int(r.get("holdings_count", 0)) > 0})
    universe_as_of = _universe_as_of(universe)
    data_end_date = dates[-1].isoformat() if dates else "unknown"
    data_start_date = dates[0].isoformat() if dates else "unknown"
    metadata = {
        **provider_metadata,
        "source_hash": _source_hash_for_run(args),
        "universe_as_of_date": universe_as_of,
        "universe_name": _universe_name(args, universe),
        "universe_ticker_count": len(universe),
        "price_ticker_count": len(tickers),
        "data_start_date": data_start_date,
        "data_end_date": data_end_date,
        "tested_factor_count": tested_factor_count,
        "effective_factor_count": effective_factor_count,
        "timing_convention": TIMING_CONVENTION,
        "caveats": CAVEATS,
        "run_config": {**vars(args), "factors": requested_factors},
        "ranking_formula": {
            "reward_weights": {"cagr": 0.20, "sharpe": 0.25, "sortino": 0.20, "calmar": 0.20},
            "penalty_weights": {"abs_max_drawdown": 0.10, "volatility": 0.05},
            "tie_breakers": ["composite_score desc", "sharpe desc", "cagr desc", "max_drawdown desc", "factor asc"],
            "missing_metric_policy": "worst normalized score; all-equal finite metrics receive 0.5; extreme positive Sortino/Calmar values are capped at 999",
        },
    }

    rank_score_by_factor = {str(row["factor"]): row.get("composite_score", 0.0) for row in rankings}
    rank_order = {str(row["factor"]): idx for idx, row in enumerate(rankings)}
    metrics_with_scores = []
    for row in metrics:
        enriched = dict(row)
        enriched["composite_score"] = rank_score_by_factor.get(str(row["factor"]), 0.0)
        metrics_with_scores.append({col: enriched.get(col, "") for col in METRIC_COLUMNS})
    metrics_with_scores.sort(key=lambda row: (rank_order.get(str(row["factor"]), 10_000), str(row["factor"])))

    write_csv_dicts(output_dir / "prices_snapshot.csv", _serialize_prices(prices), PRICE_COLUMNS)
    write_universe_snapshot(output_dir / "universe_snapshot.csv", universe)
    write_csv_dicts(output_dir / "factor_scores.csv", serialize_factor_scores(scores), FACTOR_SCORE_COLUMNS)
    write_csv_dicts(output_dir / "portfolio_returns.csv", serialize_returns(returns), PORTFOLIO_RETURN_COLUMNS)
    write_csv_dicts(output_dir / "factor_metrics.csv", metrics_with_scores, METRIC_COLUMNS)
    write_csv_dicts(output_dir / "factor_rankings.csv", rankings, RANKING_COLUMNS)
    write_csv_dicts(output_dir / "latest_holdings.csv", serialize_holdings(latest), HOLDING_COLUMNS)
    write_csv_dicts(
        output_dir / "skipped_reasons.csv",
        [{"skip_reason": key, "count": value} for key, value in sorted(Counter(skipped_reasons).items())],
        ["skip_reason", "count"],
    )
    write_json(output_dir / "run_config.json", vars(args))
    write_json(output_dir / "run_metadata.json", metadata)
    write_report(output_dir / "report.md", rankings, latest, skipped_reasons, metadata)
    write_html_report(output_dir / "report.html", rankings, latest, skipped_reasons, metadata)
    return {"output_dir": str(output_dir), "best_factor": best_factor, "latest_holdings": latest}


def _source_hash_for_run(args: argparse.Namespace) -> str | None:
    source_paths = [path for path in [args.prices_file, args.universe_file, args.fundamentals_file] if path]
    if not source_paths:
        return None
    return source_hash_for_paths(source_paths)


def _serialize_prices(prices: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {**row, "date": row["date"].isoformat() if hasattr(row["date"], "isoformat") else row["date"]}
        for row in prices
    ]


def _universe_as_of(universe: list[dict[str, object]]) -> str:
    values = sorted({str(row.get("as_of_date") or "unknown") for row in universe})
    return values[-1] if values else "unknown"


def _universe_name(args: argparse.Namespace, universe: list[dict[str, object]]) -> str:
    if args.universe_file:
        return Path(args.universe_file).stem
    sources = sorted({str(row.get("source") or "") for row in universe if row.get("source")})
    if sources:
        return ",".join(sources[:3])
    return "inferred_from_prices"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
