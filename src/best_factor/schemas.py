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
    "inactive_or_non_stock",
    "unknown_factor",
}

CAVEATS = [
    "Default live runs use free public/current-universe data and are not survivorship-bias free.",
    "Yahoo/yfinance data can be delayed, revised, rate-limited, unavailable, or subject to Yahoo terms; use for research/education only.",
    "Fundamental fields from free sources can be sparse or not point-in-time; unavailable factor rows are skipped with explicit reason codes.",
    "Coverage is measured over emitted portfolio-return periods after missing-price and eligibility skips, not over every scheduled calendar rebalance.",
    "Outputs are research artifacts, not investment advice or trade instructions.",
]

TIMING_CONVENTION = (
    "Signals at date t use data available through t; weights are formed at t and evaluated "
    "on forward close-to-close returns after t, ending at the next rebalance date."
)
