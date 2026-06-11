"""Performance metrics for factor portfolio returns."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Iterable


def compute_metrics(portfolio_returns: list[dict[str, object]], frequency: str) -> list[dict[str, object]]:
    periods_per_year = 12 if frequency == "M" else 52
    by_factor: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in portfolio_returns:
        by_factor[str(row["factor"])].append(row)
    metrics = []
    for factor, rows in sorted(by_factor.items()):
        rows.sort(key=lambda r: r["period_end"])
        returns = [float(r["return"]) for r in rows]
        equity = _equity_curve(returns)
        total = equity[-1] if equity else 1.0
        years = max(len(returns) / periods_per_year, 1 / periods_per_year)
        cagr = total ** (1 / years) - 1 if total > 0 else -1.0
        annual_return = statistics.fmean(returns) * periods_per_year if returns else 0.0
        vol = _safe_stdev(returns) * math.sqrt(periods_per_year)
        sharpe = annual_return / vol if vol > 0 else 0.0
        downside = [min(0.0, r) for r in returns]
        downside_dev = math.sqrt(statistics.fmean([d * d for d in downside])) * math.sqrt(periods_per_year) if downside else 0.0
        sortino = _cap_ratio(annual_return / downside_dev) if downside_dev > 0 else (0.0 if annual_return <= 0 else 999.0)
        mdd = max_drawdown(equity)
        # Standard Calmar uses CAGR over absolute max drawdown.  Keep
        # ``annual_return`` as a separate arithmetic-return metric for Sharpe,
        # but do not mix it into the Calmar denominator.
        calmar = _cap_ratio(cagr / abs(mdd)) if mdd < 0 else (0.0 if cagr <= 0 else 999.0)
        turnover = statistics.fmean([float(r.get("turnover", 0.0)) for r in rows]) if rows else 0.0
        coverage = sum(1 for r in rows if int(r.get("holdings_count", 0)) > 0) / len(rows) if rows else 0.0
        metrics.append(
            {
                "factor": factor,
                "cagr": cagr,
                "annual_return": annual_return,
                "volatility": vol,
                "sharpe": sharpe,
                "sortino": sortino,
                "calmar": calmar,
                "max_drawdown": mdd,
                "turnover": turnover,
                "coverage": coverage,
                "composite_score": 0.0,
            }
        )
    return metrics


def compute_holdout_metrics(
    portfolio_returns: list[dict[str, object]],
    frequency: str,
    *,
    fraction: float = 0.25,
    min_periods: int = 6,
) -> list[dict[str, object]]:
    """Compute metrics on each factor's most recent holdout window.

    The ranking winner is selected in-sample by design, so this secondary
    artifact makes recent-period robustness visible without changing the
    deterministic primary ranking contract.  For short fixture runs, the
    available tail is used and metadata should be interpreted accordingly.
    """
    if fraction <= 0 or fraction > 1:
        raise ValueError("holdout fraction must be in (0, 1]")
    by_factor: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in portfolio_returns:
        by_factor[str(row["factor"])].append(row)
    holdout_rows: list[dict[str, object]] = []
    for rows in by_factor.values():
        rows.sort(key=lambda r: r["period_end"])
        if not rows:
            continue
        tail_count = min(len(rows), max(1, min_periods, math.ceil(len(rows) * fraction)))
        holdout_rows.extend(rows[-tail_count:])
    return compute_metrics(holdout_rows, frequency)


def max_drawdown(equity: Iterable[float]) -> float:
    peak = 1.0
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def _equity_curve(returns: list[float]) -> list[float]:
    equity = [1.0]
    value = 1.0
    for ret in returns:
        value *= 1.0 + ret
        equity.append(value)
    return equity


def _safe_stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return statistics.pstdev(values)


def _cap_ratio(value: float, limit: float = 999.0) -> float:
    if not math.isfinite(value):
        return 0.0
    return max(-limit, min(limit, value))
