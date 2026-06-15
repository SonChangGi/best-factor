"""Command line interface for best-factor."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

from .calendar import rebalance_dates as build_rebalance_dates
from .data import (
    fetch_yfinance_prices,
    group_prices,
    load_fundamentals_csv,
    load_prices_csv,
    load_universe_csv,
    normalize_ticker,
    price_dates,
    source_hash_for_paths,
    write_universe_snapshot,
)
from .factors import (
    DEFAULT_FACTORS,
    FACTOR_PRESETS,
    compute_factor_scores,
    iter_factor_score_batches,
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
from .portfolio import (
    benchmark_returns_for_schedule,
    latest_holdings_for_best,
    run_backtests,
    run_backtests_from_score_batches,
    serialize_benchmark_returns,
    serialize_holdings,
    serialize_returns,
)
from .ranking import rank_factors
from .report import write_html_report, write_report
from .site import write_site_payload
from .schemas import (
    CAVEATS,
    FACTOR_SCORE_COLUMNS,
    HOLDING_COLUMNS,
    METRIC_COLUMNS,
    BENCHMARK_RETURN_COLUMNS,
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
        "--transaction-cost-model",
        choices=["one_way_notional", "portfolio_turnover"],
        default="one_way_notional",
        help=(
            "one_way_notional charges bps on buys plus sells; portfolio_turnover preserves the older "
            "0.5*sum(abs(delta weight)) convention"
        ),
    )
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
    run.add_argument("--price-chunk-size", type=int, default=100, help="ticker chunk size for yfinance price downloads")
    run.add_argument("--min-price-tickers", type=int, default=0, help="fail if fewer unique stock tickers have price data")
    run.add_argument("--min-price-coverage-ratio", type=float, default=0.0, help="fail if price coverage is below this requested-ticker ratio")
    run.add_argument(
        "--min-latest-data-coverage-ratio",
        type=float,
        default=0.0,
        help="fail if fewer tickers than this ratio share the latest available price date",
    )
    run.add_argument("--skip-factor-scores-csv", action="store_true", help="skip raw factor_scores.csv archive for large live runs")
    run.add_argument("--universe-metadata-file", help="optional JSON emitted by build_live_universe.py")
    run.add_argument(
        "--min-history-observations",
        type=int,
        default=0,
        help="diagnostic/gate: minimum trailing price rows a stock must have at the latest signal date",
    )
    run.add_argument(
        "--eligibility-adv-window",
        type=int,
        default=63,
        help="diagnostic/gate: trailing sessions used for the latest liquidity-qualified stock count",
    )
    run.add_argument(
        "--min-factor-eligible-tickers",
        type=int,
        default=0,
        help="fail if latest history+liquidity-qualified active stocks are below this count",
    )
    run.add_argument(
        "--benchmark-tickers",
        nargs="*",
        default=[],
        help="optional benchmark symbols for dashboard comparison charts, e.g. ^IXIC for Nasdaq Composite",
    )
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
        loaded_prices = load_prices_csv(price_path)
        benchmark_tickers_for_csv = set(_normalize_symbols(args.benchmark_tickers))
        benchmark_prices = _benchmark_prices_from_csv(loaded_prices, args.benchmark_tickers)
        prices = [row for row in loaded_prices if str(row.get("ticker", "")).upper() not in benchmark_tickers_for_csv]
        benchmark_provider_metadata: dict[str, object] = {}
        provider_metadata = {
            "provider": "csv",
            "provider_version": "stdlib",
            "fetched_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
            "source": f"csv:{price_path}",
            "cache_dir": str(cache_dir),
        }
    else:
        benchmark_tickers = _normalize_symbols(args.benchmark_tickers)
        tickers = _normalize_symbols(args.tickers)
        _reject_benchmark_overlap(tickers, benchmark_tickers)
        if not tickers:
            raise ValueError("--tickers are required when --provider yfinance")
        prices, provider_metadata = fetch_yfinance_prices(tickers, args.period, cache_dir, chunk_size=args.price_chunk_size)
        if benchmark_tickers:
            try:
                benchmark_prices, benchmark_provider_metadata = fetch_yfinance_prices(benchmark_tickers, args.period, cache_dir, chunk_size=args.price_chunk_size)
            except Exception as exc:
                benchmark_prices = []
                benchmark_provider_metadata = {
                    "succeeded_tickers": [],
                    "failed_tickers": benchmark_tickers,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        else:
            benchmark_prices, benchmark_provider_metadata = [], {}
    if not prices:
        raise ValueError("no prices loaded")
    tickers = sorted({str(row["ticker"]) for row in prices})
    requested_count = max(int(provider_metadata.get("requested_ticker_count") or len(getattr(args, "tickers", []) or tickers)), len(tickers))
    price_coverage_ratio = _safe_ratio(len(tickers), requested_count)
    if int(args.min_price_tickers or 0) > 0 and len(tickers) < int(args.min_price_tickers):
        raise ValueError(
            f"price_ticker_count {len(tickers)} is below --min-price-tickers {args.min_price_tickers} "
            f"for requested_ticker_count {requested_count}"
        )
    if float(args.min_price_coverage_ratio or 0.0) > 0 and price_coverage_ratio < float(args.min_price_coverage_ratio):
        raise ValueError(
            f"price_coverage_ratio {price_coverage_ratio:.4f} is below --min-price-coverage-ratio "
            f"{float(args.min_price_coverage_ratio):.4f} for {len(tickers)}/{requested_count} price tickers"
        )
    latest_price_coverage = _latest_price_coverage(prices)
    latest_data_coverage_ratio = float(latest_price_coverage.get("latest_data_coverage_ratio") or 0.0)
    if (
        float(args.min_latest_data_coverage_ratio or 0.0) > 0
        and latest_data_coverage_ratio < float(args.min_latest_data_coverage_ratio)
    ):
        raise ValueError(
            f"latest_data_coverage_ratio {latest_data_coverage_ratio:.4f} is below "
            f"--min-latest-data-coverage-ratio {float(args.min_latest_data_coverage_ratio):.4f}"
        )
    universe = load_universe_csv(args.universe_file, tickers)
    universe_build_metadata = _read_json_file(args.universe_metadata_file)
    fundamentals = load_fundamentals_csv(args.fundamentals_file)
    dates = price_dates(prices)
    schedule = build_rebalance_dates(dates, args.rebalance)
    if len(schedule) < 2:
        raise ValueError("not enough price history to form at least two rebalance dates")
    eligibility_diagnostics = _stock_eligibility_diagnostics(
        prices,
        universe,
        schedule,
        min_dollar_volume=float(args.min_dollar_volume or 0.0),
        min_history_observations=int(args.min_history_observations or 0),
        adv_window=int(args.eligibility_adv_window or 63),
    )
    latest_factor_eligible = int(eligibility_diagnostics.get("latest_factor_eligible_ticker_count") or 0)
    if int(args.min_factor_eligible_tickers or 0) > 0 and latest_factor_eligible < int(args.min_factor_eligible_tickers):
        raise ValueError(
            f"latest_factor_eligible_ticker_count {latest_factor_eligible} is below "
            f"--min-factor-eligible-tickers {int(args.min_factor_eligible_tickers)}"
        )
    benchmark_tickers = _normalize_symbols(args.benchmark_tickers)

    if args.skip_factor_scores_csv:
        scores: list[dict[str, object]] = []
        score_batches = iter_factor_score_batches(prices, schedule[:-1], fundamentals, requested_factors, requested_factors)
        backtest = run_backtests_from_score_batches(
            prices,
            universe,
            score_batches,
            schedule,
            args.top_n,
            args.weighting,
            args.min_market_cap,
            args.min_dollar_volume,
            args.transaction_cost_bps,
            args.transaction_cost_model,
            int(args.eligibility_adv_window or 63),
        )
    else:
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
            args.transaction_cost_model,
            int(args.eligibility_adv_window or 63),
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
    benchmark_returns = [
        row
        for ticker in benchmark_tickers
        for row in benchmark_returns_for_schedule(benchmark_prices, ticker, _benchmark_label(ticker), schedule)
    ]

    metadata = {
        **provider_metadata,
        "source_hash": _source_hash_for_run(args),
        "universe_as_of_date": universe_as_of,
        "universe_name": _universe_name(args, universe),
        "universe_ticker_count": len(universe),
        "price_ticker_count": len(tickers),
        "requested_ticker_count": requested_count,
        "min_price_tickers": int(args.min_price_tickers or 0),
        "min_price_coverage_ratio": float(args.min_price_coverage_ratio or 0.0),
        "min_latest_data_coverage_ratio": float(args.min_latest_data_coverage_ratio or 0.0),
        "price_coverage_ratio": price_coverage_ratio,
        **latest_price_coverage,
        "rankable_stock_universe_count": _rankable_stock_universe_count(universe, tickers),
        **eligibility_diagnostics,
        "min_factor_eligible_tickers": int(args.min_factor_eligible_tickers or 0),
        **_universe_build_public_metadata(universe_build_metadata),
        "factor_scores_archive": "skipped_for_large_live_run" if args.skip_factor_scores_csv else "written",
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
        "market_cap_filter_status": _market_cap_filter_status(args, universe),
        "filter_fallback_reason": str(args.filter_fallback_reason or "none"),
        "current_screen_note": (
            "Universe membership and market-cap filters use the supplied/current metadata snapshot; "
            "they are not historical point-in-time constituent or market-cap screens."
        ),
        "coverage_denominator": "emitted_portfolio_return_periods_per_factor_including_zero_holding_attempts",
        "transaction_cost_bps": float(args.transaction_cost_bps or 0.0),
        "transaction_cost_model": args.transaction_cost_model,
        "transaction_cost_note": _transaction_cost_note(args.transaction_cost_model),
        "rebalance_frequency": args.rebalance,
        "benchmark_tickers": benchmark_tickers,
        "benchmark_label": _benchmark_label(benchmark_tickers[0]) if benchmark_tickers else None,
        "benchmark_return_count": len(benchmark_returns),
        "benchmark_succeeded_tickers": benchmark_provider_metadata.get("succeeded_tickers", benchmark_tickers if benchmark_returns else []),
        "benchmark_failed_tickers": benchmark_provider_metadata.get("failed_tickers", [] if benchmark_returns else benchmark_tickers),
        "benchmark_error": benchmark_provider_metadata.get("error"),
        "benchmark_note": (
            "Nasdaq benchmark data is used only for relative context; ^IXIC is preferred and ONEQ/QQQ "
            "are explicit free-data proxy fallbacks if index history is unavailable. Benchmark tickers "
            "are never included in stock selection, holdings, or factor ranking."
        ),
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
    if not args.skip_factor_scores_csv:
        write_csv_dicts(output_dir / "factor_scores.csv", serialize_factor_scores(scores), FACTOR_SCORE_COLUMNS)
    write_csv_dicts(output_dir / "portfolio_returns.csv", serialize_returns(returns), PORTFOLIO_RETURN_COLUMNS)
    write_csv_dicts(output_dir / "benchmark_returns.csv", serialize_benchmark_returns(benchmark_returns), BENCHMARK_RETURN_COLUMNS)
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


def _read_json_file(path: str | None) -> dict[str, object]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"metadata JSON must be an object: {path}")
    return payload


def _latest_price_coverage(prices: list[dict[str, object]]) -> dict[str, object]:
    grouped = group_prices(prices)
    latest_date = max((row["date"] for row in prices if hasattr(row.get("date"), "isoformat")), default=None)
    if latest_date is None or not grouped:
        return {"latest_data_ticker_count": 0, "latest_data_coverage_ratio": 0.0}
    count = sum(1 for rows in grouped.values() if rows and rows[-1]["date"] == latest_date)
    return {"latest_data_ticker_count": count, "latest_data_coverage_ratio": _safe_ratio(count, len(grouped))}


def _stock_eligibility_diagnostics(
    prices: list[dict[str, object]],
    universe: list[dict[str, object]],
    schedule: list[dt.date],
    *,
    min_dollar_volume: float,
    min_history_observations: int,
    adv_window: int,
) -> dict[str, object]:
    """Summarize whether the priced universe is also usable by factor/liquidity gates.

    Price coverage alone can overstate the economically analyzable universe.  This
    diagnostic counts active priced stocks that have enough trailing observations
    and pass the same trailing ADV liquidity floor used in portfolio selection at
    each signal date.  The live workflow gates on the latest signal date while
    still exposing the rebalance-window distribution for interpretation.
    """
    grouped = group_prices(prices)
    active_tickers = {
        str(row.get("ticker") or "").upper()
        for row in universe
        if _is_active_stock_row(row) and str(row.get("ticker") or "").upper() in grouped
    }
    signal_dates = list(schedule[:-1])
    min_history_observations = max(0, int(min_history_observations or 0))
    adv_window = max(1, int(adv_window or 63))
    counts: list[int] = []
    history_counts: list[int] = []
    liquidity_counts: list[int] = []
    latest_breakdown = {
        "history_qualified_ticker_count": 0,
        "liquidity_qualified_ticker_count": 0,
        "latest_factor_eligible_ticker_count": 0,
        "factor_eligibility_signal_date": "",
    }
    for signal_date in signal_dates:
        history_ok: set[str] = set()
        liquidity_ok: set[str] = set()
        for ticker in active_tickers:
            rows = grouped.get(ticker, [])
            trailing = [row for row in rows if row["date"] <= signal_date]
            if len(trailing) >= min_history_observations:
                history_ok.add(ticker)
            if min_dollar_volume <= 0 or _average_dollar_volume(trailing, adv_window) >= min_dollar_volume:
                liquidity_ok.add(ticker)
        eligible = history_ok & liquidity_ok
        history_counts.append(len(history_ok))
        liquidity_counts.append(len(liquidity_ok))
        counts.append(len(eligible))
        latest_breakdown = {
            "history_qualified_ticker_count": len(history_ok),
            "liquidity_qualified_ticker_count": len(liquidity_ok),
            "latest_factor_eligible_ticker_count": len(eligible),
            "factor_eligibility_signal_date": signal_date.isoformat(),
        }
    return {
        "min_history_observations": min_history_observations,
        "eligibility_adv_window": adv_window,
        "eligibility_min_dollar_volume": float(min_dollar_volume or 0.0),
        "active_priced_stock_count": len(active_tickers),
        **latest_breakdown,
        "rebalance_eligible_min_count": min(counts) if counts else 0,
        "rebalance_eligible_median_count": statistics.median(counts) if counts else 0,
        "rebalance_eligible_latest_count": counts[-1] if counts else 0,
        "rebalance_history_qualified_latest_count": history_counts[-1] if history_counts else 0,
        "rebalance_liquidity_qualified_latest_count": liquidity_counts[-1] if liquidity_counts else 0,
        "factor_eligibility_note": (
            "Latest active priced stocks that meet the configured trailing-history observation floor and "
            "the same trailing average-dollar-volume liquidity floor used for portfolio selection."
        ),
    }


def _average_dollar_volume(rows: list[dict[str, object]], window: int) -> float:
    if len(rows) < window:
        return 0.0
    values = []
    for row in rows[-window:]:
        try:
            values.append(float(row.get("volume", 0) or 0) * float(row.get("adj_close", 0) or 0))
        except (TypeError, ValueError):
            values.append(0.0)
    return sum(values) / len(values) if values else 0.0


def _safe_ratio(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator > 0 else 0.0


def _rankable_stock_universe_count(universe: list[dict[str, object]], price_tickers: list[str]) -> int:
    priced = set(price_tickers)
    return sum(1 for row in universe if str(row.get("ticker") or "").upper() in priced and _is_active_stock_row(row))


def _is_active_stock_row(row: dict[str, object]) -> bool:
    active_value = row.get("active", True)
    if isinstance(active_value, bool):
        active = active_value
    elif isinstance(active_value, (int, float)):
        active = active_value != 0
    else:
        text = str(active_value).strip().lower()
        if text in {"", "1", "true", "t", "yes", "y", "active"}:
            active = True
        elif text in {"0", "false", "f", "no", "n", "inactive"}:
            active = False
        else:
            active = bool(text)
    asset_type = str(row.get("asset_type", "stock") or "stock").strip().lower()
    return active and asset_type in {"stock", "equity", "common_stock", "common stock"}


def _universe_build_public_metadata(payload: dict[str, object]) -> dict[str, object]:
    keys = {
        "universe_source_urls",
        "symbol_directory_source_hash",
        "raw_symbol_count",
        "common_stock_candidate_count",
        "excluded_symbol_counts",
        "committed_priority_ticker_count",
        "selected_universe_ticker_count",
        "min_validated_symbol_count",
        "invalid_ticker_count",
        "universe_construction_note",
    }
    return {f"universe_build_{key}": payload[key] for key in keys if key in payload}


def _source_hash_for_run(args: argparse.Namespace) -> str | None:
    source_paths = [path for path in [args.prices_file, args.universe_file, args.fundamentals_file] if path]
    if not source_paths:
        return None
    return source_hash_for_paths(source_paths)


def _normalize_symbols(symbols: list[str] | tuple[str, ...] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in symbols or []:
        symbol = normalize_ticker(raw)
        if symbol and symbol not in seen:
            seen.add(symbol)
            out.append(symbol)
    return out


def _reject_benchmark_overlap(stock_tickers: list[str], benchmark_tickers: list[str]) -> None:
    overlap = sorted(set(stock_tickers) & set(benchmark_tickers))
    if overlap:
        raise ValueError(
            "benchmark ticker(s) must not also be stock-universe tickers: "
            + ", ".join(overlap)
            + ". Pass benchmarks only through --benchmark-tickers."
        )


def _benchmark_prices_from_csv(prices: list[dict[str, object]], symbols: list[str] | tuple[str, ...] | None) -> list[dict[str, object]]:
    wanted = set(_normalize_symbols(symbols))
    if not wanted:
        return []
    return [row for row in prices if str(row.get("ticker", "")).upper() in wanted]


def _benchmark_label(ticker: str) -> str:
    labels = {
        "^IXIC": "Nasdaq Composite",
        "ONEQ": "Nasdaq Composite ETF proxy",
        "^NDX": "Nasdaq-100",
        "QQQ": "Nasdaq-100 ETF proxy",
    }
    return labels.get(str(ticker).upper(), str(ticker).upper())


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


def _market_cap_filter_status(args: argparse.Namespace, universe: list[dict[str, object]]) -> str:
    if float(getattr(args, "min_market_cap", 0.0) or 0.0) > 0:
        return "applied_current_metadata_not_point_in_time"
    if getattr(args, "market_cap_filter_attempted", False):
        return (
            "not_applied_metadata_insufficient; dashboard scope is current common-stock plus liquidity, "
            "not a large-cap screen"
        )
    finite = 0
    for row in universe:
        try:
            if math.isfinite(float(row.get("market_cap", math.nan))):
                finite += 1
        except (TypeError, ValueError):
            continue
    return f"not_requested; finite_market_cap_rows={finite}"


def _transaction_cost_note(model: str) -> str:
    if model == "one_way_notional":
        return (
            "Transaction-cost bps are charged on one-way traded notional: "
            "sum(abs(delta weights)). A full cash-to-portfolio buy costs 1x notional; "
            "a full disjoint replacement costs 2x notional."
        )
    return (
        "Transaction-cost bps are charged on portfolio turnover: "
        "0.5 * sum(abs(delta weights)); retained for backward-compatible research comparisons."
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
