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
from .factors import (
    DEFAULT_FACTORS,
    FACTOR_PRESETS,
    compute_factor_scores,
    factor_catalog,
    factor_category_counts,
    factor_family_summary,
    factor_kind_counts,
    factor_names_for_preset,
    serialize_factor_scores,
    validate_factor_names,
)
from .io_utils import ensure_dir, write_csv_dicts, write_json
from .metrics import compute_holdout_metrics, compute_metrics
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
    run.add_argument(
        "--market-cap-filter-attempted",
        action="store_true",
        help="record that a market-cap-filtered run was attempted before this final run",
    )
    run.add_argument(
        "--filter-fallback-reason",
        default="",
        help="optional reason when the final run falls back from a stricter filter path",
    )
    run.add_argument("--tickers", nargs="*", default=[])
    run.add_argument("--period", default="5y")
    run.add_argument("--cache-dir", default=".cache/best-factor")
    run.add_argument(
        "--factor-preset",
        choices=sorted(FACTOR_PRESETS),
        default="zoo",
        help="factor library preset to run when --factors is not supplied (default: zoo)",
    )
    run.add_argument("--factors", nargs="+", default=None, help="explicit factor names; overrides --factor-preset")

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
    if args.factors:
        requested_factors = validate_factor_names(args.factors)
        factor_preset = "explicit"
    else:
        requested_factors = factor_names_for_preset(args.factor_preset)
        factor_preset = args.factor_preset
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
    holdout_metrics = compute_holdout_metrics(returns, args.rebalance, fraction=0.25, min_periods=6)
    skipped_zero_coverage = {str(row["factor"]): "zero_coverage" for row in metrics if float(row.get("coverage", 0.0)) <= 0}
    rankable_metrics = [row for row in metrics if float(row.get("coverage", 0.0)) > 0]
    rankings = rank_factors(rankable_metrics)
    holdout_rankings = rank_factors([row for row in holdout_metrics if float(row.get("coverage", 0.0)) > 0])
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
    market_cap_effective = float(args.min_market_cap or 0.0) > 0
    market_cap_attempted = bool(args.market_cap_filter_attempted or market_cap_effective)
    holdout_rank_by_factor = {str(row["factor"]): int(row["rank"]) for row in holdout_rankings}
    holdout_metric_by_factor = {str(row["factor"]): row for row in holdout_rankings}
    best_holdout = holdout_metric_by_factor.get(best_factor, {})

    metadata = {
        **provider_metadata,
        "source_hash": _source_hash_for_run(args),
        "universe_as_of_date": universe_as_of,
        "universe_name": _universe_name(args, universe),
        "universe_ticker_count": len(universe),
        "price_ticker_count": len(tickers),
        "universe_scope_note": (
            "Universe is the supplied or committed current ticker set for this run; "
            "it is not the whole US equity market and not historical point-in-time constituents."
        ),
        "data_start_date": data_start_date,
        "data_end_date": data_end_date,
        "universe_is_point_in_time": False,
        "market_cap_filter_basis": _market_cap_filter_basis(args, universe),
        "market_cap_filter_attempted": market_cap_attempted,
        "market_cap_filter_effective": market_cap_effective,
        "filter_fallback_reason": str(args.filter_fallback_reason or "none"),
        "current_screen_note": (
            "Universe membership and market-cap filters use the supplied/current metadata snapshot; "
            "they are not historical point-in-time constituent or market-cap screens."
        ),
        "coverage_denominator": "emitted_portfolio_return_periods_per_factor_including_zero_holding_attempts",
        "tested_factor_count": tested_factor_count,
        "effective_factor_count": effective_factor_count,
        "factor_preset": factor_preset,
        "requested_factor_preset": args.factor_preset,
        "factor_library_size": len(DEFAULT_FACTORS),
        "selected_factor_count": tested_factor_count,
        "factor_category_counts": factor_category_counts(requested_factors),
        "factor_kind_counts": factor_kind_counts(requested_factors),
        "factor_family_summary": factor_family_summary(requested_factors),
        "factor_catalog": factor_catalog(requested_factors),
        "skip_resolution_note": (
            "Actionable skips are recorded by reason. Missing point-in-time fundamentals, current-universe bias, "
            "same-close timing, and free-provider availability remain explicit research constraints; "
            "OHLCV-only families avoid those fundamental skips when fundamentals are unavailable."
        ),
        "factor_library_note": (
            "Factor-zoo mode ranks the best factor among the tested candidate definitions in this run; "
            "it is exploratory and not an out-of-sample or multiple-testing-adjusted anomaly discovery claim."
        ),
        "holdout_validation": {
            "method": "recent_tail_by_factor",
            "holdout_fraction": 0.25,
            "min_periods": 6,
            "best_factor_holdout_rank": holdout_rank_by_factor.get(best_factor),
            "best_factor_holdout_cagr": best_holdout.get("cagr"),
            "best_factor_holdout_sharpe": best_holdout.get("sharpe"),
            "holdout_ranked_factor_count": len(holdout_rankings),
            "interpretation": (
                "Secondary robustness check on each factor's most recent return periods; "
                "the primary winner remains an in-sample exploratory result, not a true untouched out-of-sample test."
            ),
        },
        "timing_convention": TIMING_CONVENTION,
        "caveats": CAVEATS,
        "run_config": {
            **vars(args),
            "factors": requested_factors,
            "factor_preset": factor_preset,
            "requested_factor_preset": args.factor_preset,
        },
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
    holdout_score_by_factor = {str(row["factor"]): row.get("composite_score", 0.0) for row in holdout_rankings}
    holdout_order = {str(row["factor"]): idx for idx, row in enumerate(holdout_rankings)}
    holdout_metrics_with_scores = []
    for row in holdout_metrics:
        enriched = dict(row)
        enriched["composite_score"] = holdout_score_by_factor.get(str(row["factor"]), 0.0)
        holdout_metrics_with_scores.append({col: enriched.get(col, "") for col in METRIC_COLUMNS})
    holdout_metrics_with_scores.sort(key=lambda row: (holdout_order.get(str(row["factor"]), 10_000), str(row["factor"])))

    write_csv_dicts(output_dir / "factor_metrics.csv", metrics_with_scores, METRIC_COLUMNS)
    write_csv_dicts(output_dir / "factor_rankings.csv", rankings, RANKING_COLUMNS)
    write_csv_dicts(output_dir / "factor_holdout_metrics.csv", holdout_metrics_with_scores, METRIC_COLUMNS)
    write_csv_dicts(output_dir / "factor_holdout_rankings.csv", holdout_rankings, RANKING_COLUMNS)
    write_csv_dicts(output_dir / "latest_holdings.csv", serialize_holdings(latest), HOLDING_COLUMNS)
    write_csv_dicts(
        output_dir / "skipped_reasons.csv",
        [{"skip_reason": key, "count": value} for key, value in sorted(Counter(skipped_reasons).items())],
        ["skip_reason", "count"],
    )
    write_json(
        output_dir / "run_config.json",
        {
            **vars(args),
            "factors": requested_factors,
            "factor_preset": factor_preset,
            "requested_factor_preset": args.factor_preset,
        },
    )
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


def _market_cap_filter_basis(args: argparse.Namespace, universe: list[dict[str, object]]) -> str:
    if float(getattr(args, "min_market_cap", 0.0) or 0.0) <= 0:
        return "not_applied"
    sources = {str(row.get("source") or "").lower() for row in universe}
    if any("yfinance" in source for source in sources):
        return "current_yfinance_metadata_screen_not_point_in_time"
    return "supplied_universe_metadata_screen_not_verified_point_in_time"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
