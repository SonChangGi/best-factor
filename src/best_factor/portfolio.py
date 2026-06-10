"""Long-only portfolio construction and no-lookahead backtesting."""
from __future__ import annotations

import datetime as dt
import math
from collections import Counter, defaultdict
from typing import Iterable

from .data import group_prices
from .factors import factor_names, rows_for_factor_date
from .schemas import HOLDING_COLUMNS, PORTFOLIO_RETURN_COLUMNS


def run_backtests(
    prices: list[dict[str, object]],
    universe: list[dict[str, object]],
    scores: list[dict[str, object]],
    rebalance_dates: list[dt.date],
    top_n: int,
    weighting: str = "equal",
    min_market_cap: float = 0.0,
    min_dollar_volume: float = 0.0,
    transaction_cost_bps: float = 0.0,
) -> dict[str, object]:
    grouped = group_prices(prices)
    universe_by_ticker = {str(row["ticker"]): row for row in universe}
    all_factor_names = factor_names(scores)
    all_holdings: list[dict[str, object]] = []
    all_returns: list[dict[str, object]] = []
    skipped: Counter[str] = Counter()
    previous_holdings: dict[str, dict[str, float]] = {factor: {} for factor in all_factor_names}

    if len(rebalance_dates) < 2:
        return {"holdings": [], "returns": [], "skipped_reasons": {"insufficient_history": 1}}

    for factor in all_factor_names:
        for start, end in zip(rebalance_dates, rebalance_dates[1:]):
            score_rows = rows_for_factor_date(scores, factor, start)
            selected, reasons = _select_holdings(
                score_rows,
                grouped,
                universe_by_ticker,
                start,
                top_n,
                weighting,
                min_market_cap,
                min_dollar_volume,
            )
            skipped.update(reasons)
            tradable = []
            for holding in selected:
                ticker = str(holding["ticker"])
                ret = _forward_return(grouped[ticker], start, end)
                if ret is None:
                    start_prices = {r["date"] for r in grouped[ticker]}
                    skipped["missing_rebalance_price" if start not in start_prices else "missing_exit_price"] += 1
                    continue
                tradable.append((holding, ret))
            if not tradable:
                skipped["empty_after_filters"] += 1
                continue
            weight_total = sum(float(holding["weight"]) for holding, _ in tradable)
            if weight_total <= 0:
                skipped["empty_after_filters"] += 1
                continue
            tradable = [({**holding, "weight": float(holding["weight"]) / weight_total}, ret) for holding, ret in tradable]
            current_holdings = {str(holding["ticker"]): float(holding["weight"]) for holding, _ in tradable}
            turnover = _turnover(previous_holdings[factor], current_holdings)
            period_return = 0.0
            for holding, ret in tradable:
                ticker = str(holding["ticker"])
                period_return += float(holding["weight"]) * ret
                all_holdings.append(
                    {
                        "rebalance_date": start,
                        "factor": factor,
                        "ticker": ticker,
                        "weight": float(holding["weight"]),
                        "score": float(holding["score"]),
                        "price_date_used": start,
                    }
                )
            cost = (transaction_cost_bps / 10000.0) * turnover
            all_returns.append(
                {
                    "factor": factor,
                    "period_start": start,
                    "period_end": end,
                    "return": period_return - cost,
                    "turnover": turnover,
                    "holdings_count": len(tradable),
                }
            )
            previous_holdings[factor] = current_holdings
    return {"holdings": all_holdings, "returns": all_returns, "skipped_reasons": dict(skipped)}


def latest_holdings_for_best(all_holdings: list[dict[str, object]], best_factor: str) -> list[dict[str, object]]:
    rows = [h for h in all_holdings if h["factor"] == best_factor]
    if not rows:
        return []
    latest = max(h["rebalance_date"] for h in rows)
    return sorted([h for h in rows if h["rebalance_date"] == latest], key=lambda h: (-float(h["weight"]), str(h["ticker"])))


def serialize_holdings(rows: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in rows:
        d = {col: row.get(col, "") for col in HOLDING_COLUMNS}
        for key in ("rebalance_date", "price_date_used"):
            if hasattr(d[key], "isoformat"):
                d[key] = d[key].isoformat()
        out.append(d)
    return out


def serialize_returns(rows: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in rows:
        d = {col: row.get(col, "") for col in PORTFOLIO_RETURN_COLUMNS}
        for key in ("period_start", "period_end"):
            if hasattr(d[key], "isoformat"):
                d[key] = d[key].isoformat()
        out.append(d)
    return out


def _select_holdings(
    score_rows: list[dict[str, object]],
    grouped_prices: dict[str, list[dict[str, object]]],
    universe_by_ticker: dict[str, dict[str, object]],
    signal_date: dt.date,
    top_n: int,
    weighting: str,
    min_market_cap: float,
    min_dollar_volume: float,
) -> tuple[list[dict[str, object]], Counter[str]]:
    reasons: Counter[str] = Counter()
    candidates = []
    for row in score_rows:
        ticker = str(row["ticker"])
        if not row.get("eligible"):
            reasons[str(row.get("skip_reason") or "provider_error")] += 1
            continue
        universe = universe_by_ticker.get(ticker, {})
        if ticker not in universe_by_ticker or not _is_active_stock(universe):
            reasons["inactive_or_non_stock"] += 1
            continue
        market_cap = universe.get("market_cap", math.nan)
        if min_market_cap > 0:
            if not isinstance(market_cap, (int, float)) or math.isnan(float(market_cap)):
                reasons["market_cap_unavailable"] += 1
                continue
            if float(market_cap) < min_market_cap:
                reasons["market_cap_below_min"] += 1
                continue
        if min_dollar_volume > 0:
            adv = _average_dollar_volume(grouped_prices.get(ticker, []), signal_date, 63)
            if adv < min_dollar_volume:
                reasons["insufficient_volume"] += 1
                continue
        candidates.append({"ticker": ticker, "score": float(row["score"])})
    candidates.sort(key=lambda r: (-float(r["score"]), str(r["ticker"])))
    selected = candidates[: max(0, top_n)]
    if not selected:
        return [], reasons
    if len(candidates) < top_n:
        reasons["not_enough_assets"] += 1
    weights = _weights(selected, weighting)
    for row, weight in zip(selected, weights):
        row["weight"] = weight
    return selected, reasons


def _weights(selected: list[dict[str, object]], weighting: str) -> list[float]:
    if weighting == "equal" or len(selected) == 1:
        return [1.0 / len(selected)] * len(selected)
    if weighting != "score":
        raise ValueError("weighting must be 'equal' or 'score'")
    scores = [float(row["score"]) for row in selected]
    lo = min(scores)
    span = max(scores) - lo
    if span <= 0:
        return [1.0 / len(selected)] * len(selected)
    # Add a small positive baseline so every selected long-only holding gets
    # an investable positive weight. Pure min-shifting gives the lowest scored
    # selected name an exact zero weight, which is misleading in holdings
    # reports and effectively turns top-N into top-(N-1).
    baseline = span * 0.01
    shifted = [score - lo + baseline for score in scores]
    if sum(shifted) <= 0:
        return [1.0 / len(selected)] * len(selected)
    total = sum(shifted)
    return [v / total for v in shifted]


def _forward_return(rows: list[dict[str, object]], start: dt.date, end: dt.date) -> float | None:
    by_date = {row["date"]: float(row["adj_close"]) for row in rows}
    if start not in by_date or end not in by_date or by_date[start] <= 0:
        return None
    return by_date[end] / by_date[start] - 1.0


def _average_dollar_volume(rows: list[dict[str, object]], signal_date: dt.date, window: int) -> float:
    eligible = [r for r in rows if r["date"] <= signal_date]
    if len(eligible) < window:
        return 0.0
    values = [float(r.get("volume", 0) or 0) * float(r["adj_close"]) for r in eligible[-window:]]
    return sum(values) / len(values)


def _turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    tickers = set(previous) | set(current)
    return 0.5 * sum(abs(current.get(t, 0.0) - previous.get(t, 0.0)) for t in tickers)


def _is_active_stock(universe: dict[str, object]) -> bool:
    active = _parse_active(universe.get("active", True))
    asset_type = str(universe.get("asset_type", "stock") or "stock").strip().lower()
    return active and asset_type in {"stock", "equity", "common_stock", "common stock"}


def _parse_active(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"", "1", "true", "t", "yes", "y", "active"}:
        return True
    if text in {"0", "false", "f", "no", "n", "inactive"}:
        return False
    return bool(text)
