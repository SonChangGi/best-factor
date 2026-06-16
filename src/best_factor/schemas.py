"""Canonical schemas and stable reason codes for output artifacts."""

PRICE_COLUMNS = [
    "ticker",
    "date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "source",
    "fetched_at",
]

UNIVERSE_COLUMNS = [
    "ticker",
    "name",
    "exchange",
    "asset_type",
    "active",
    "market_cap",
    "sector",
    "source",
    "as_of_date",
]

FACTOR_SCORE_COLUMNS = [
    "factor",
    "ticker",
    "signal_date",
    "score",
    "rank",
    "eligible",
    "skip_reason",
]

HOLDING_COLUMNS = [
    "rebalance_date",
    "factor",
    "ticker",
    "weight",
    "score",
    "price_date_used",
]

PORTFOLIO_RETURN_COLUMNS = [
    "factor",
    "period_start",
    "period_end",
    "return",
    "turnover",
    "holdings_count",
    "skip_reason",
]

BENCHMARK_RETURN_COLUMNS = [
    "benchmark",
    "ticker",
    "period_start",
    "period_end",
    "return",
    "price_date_start",
    "price_date_end",
    "skip_reason",
]

METRIC_COLUMNS = [
    "factor",
    "cagr",
    "annual_return",
    "volatility",
    "sharpe",
    "sortino",
    "calmar",
    "max_drawdown",
    "turnover",
    "coverage",
    "composite_score",
]

RANKING_COLUMNS = ["rank", *METRIC_COLUMNS]

SKIP_REASONS = {
    "missing_fundamentals",
    "insufficient_history",
    "insufficient_volume",
    "market_cap_unavailable",
    "market_cap_below_min",
    "empty_after_filters",
    "provider_error",
    "not_enough_assets",
    "missing_rebalance_price",
    "missing_exit_price",
    "invalid_period_missing_price",
    "inactive_or_non_stock",
    "unknown_factor",
    "zero_coverage:<factor>",
}

CAVEATS = [
    "Default live dashboard runs use a validated current Nasdaq Trader common-stock screen with configured price/factor-eligibility gates; it is still not survivorship-bias free or historical point-in-time membership.",
    "Yahoo/yfinance and direct Yahoo chart data can be delayed, revised, rate-limited, unavailable, or subject to Yahoo terms; use for research/education only.",
    "The live updater uses yfinance first and can fill missing tickers through a direct Yahoo chart JSON path, then still hard-fails when too few requested stocks return prices or latest-date coverage is too low.",
    "Live runs also publish history- and liquidity-qualified stock counts; the latest eligible count is a stronger diagnostic than raw price coverage, but early rebalance windows can still have smaller effective universes.",
    "Live OHLC prices are scaled to the adjusted-close basis before scoring OHLC-derived factors so dividends/splits do not mix raw and adjusted price scales.",
    "Fundamental fields from free sources can be sparse or not point-in-time; unavailable factor rows are skipped with explicit reason codes.",
    "Factor-zoo mode evaluates many related candidates; the selected winner is best among tested candidates in this run. Recent-tail holdout rank is only a robustness diagnostic, not fully untouched out-of-sample validation, and the winner may reflect multiple-testing/data-snooping.",
    "Coverage is measured as non-empty portfolio-return periods divided by attempted scheduled periods; dynamic diagnostics may use zero_coverage:<factor> reason codes.",
    "Outputs are research artifacts, not investment advice or trade instructions.",
    "Current free-provider universe and market-cap metadata are current-screen inputs, not historical point-in-time membership or point-in-time market capitalization.",
    "Default transaction-cost modeling charges bps on one-way traded notional; it is still a simplified close-to-close cost model and does not include bid-ask spread, market impact, taxes, borrow, or participation limits.",
    "Latest portfolio capacity uses a simple 5%/10% trailing ADV participation heuristic for the displayed weights; it is not an order-book, market-impact, tax, borrow, or broker execution model.",
]

TIMING_CONVENTION = (
    "Research convention: signals at date t use closing data available through t; reported returns are "
    "close-to-close from t to the next rebalance close. This is not an intraday trade-execution model "
    "and same-close portfolio formation can be optimistic versus executable next-session trading."
)
