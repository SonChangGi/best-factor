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
    "Default live runs use free public/current-universe data and are not survivorship-bias free.",
    "Yahoo/yfinance data can be delayed, revised, rate-limited, unavailable, or subject to Yahoo terms; use for research/education only.",
    "Fundamental fields from free sources can be sparse or not point-in-time; unavailable factor rows are skipped with explicit reason codes.",
    "Factor-zoo mode evaluates many related candidates; the selected winner is best among tested candidates in this run, not out-of-sample validated, and may reflect multiple-testing/data-snooping.",
    "Coverage is measured as non-empty portfolio-return periods divided by attempted scheduled periods; dynamic diagnostics may use zero_coverage:<factor> reason codes.",
    "Outputs are research artifacts, not investment advice or trade instructions.",
    "Current yfinance universe and market-cap metadata are current-screen inputs, not historical point-in-time membership or point-in-time market capitalization.",
]

TIMING_CONVENTION = (
    "Research convention: signals at date t use closing data available through t; reported returns are "
    "close-to-close from t to the next rebalance close. This is not an intraday trade-execution model "
    "and same-close portfolio formation can be optimistic versus executable next-session trading."
)
