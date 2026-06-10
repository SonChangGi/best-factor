"""Deterministic multi-metric factor ranking."""
from __future__ import annotations

import math
from copy import deepcopy

REWARD_WEIGHTS = {
    "cagr": 0.20,
    "sharpe": 0.25,
    "sortino": 0.20,
    "calmar": 0.20,
}
PENALTY_WEIGHTS = {
    "max_drawdown_abs": 0.10,
    "volatility": 0.05,
}


def rank_factors(metrics: list[dict[str, object]]) -> list[dict[str, object]]:
    rows = deepcopy(metrics)
    reward_scores = {metric: _normalized(rows, metric, higher_is_better=True) for metric in REWARD_WEIGHTS}
    drawdown_values = []
    for row in rows:
        value = _finite(row.get("max_drawdown"))
        drawdown_values.append(abs(value) if value is not None else math.nan)
    penalty_inputs = {
        "max_drawdown_abs": drawdown_values,
        "volatility": [_finite(row.get("volatility")) for row in rows],
    }
    penalty_scores = {metric: _normalized_values(values, higher_is_better=False) for metric, values in penalty_inputs.items()}
    for idx, row in enumerate(rows):
        score = 0.0
        for metric, weight in REWARD_WEIGHTS.items():
            score += weight * reward_scores[metric][idx]
        for metric, weight in PENALTY_WEIGHTS.items():
            score += weight * penalty_scores[metric][idx]
        row["composite_score"] = score
    rows.sort(key=_ranking_key)
    ranked = []
    for rank, row in enumerate(rows, start=1):
        ranked.append({"rank": rank, **row})
    return ranked


def _ranking_key(row: dict[str, object]) -> tuple[float, float, float, float, str]:
    return (
        -_number(row.get("composite_score")),
        -_number(row.get("sharpe")),
        -_number(row.get("cagr")),
        -_number(row.get("max_drawdown")),  # less negative is better
        str(row.get("factor", "")),
    )


def _normalized(rows: list[dict[str, object]], metric: str, higher_is_better: bool) -> list[float]:
    return _normalized_values([_finite(row.get(metric)) for row in rows], higher_is_better)


def _normalized_values(values: list[float | None], higher_is_better: bool) -> list[float]:
    finite = [v for v in values if v is not None and math.isfinite(v)]
    if not finite:
        return [0.0 for _ in values]
    lo = min(finite)
    hi = max(finite)
    out = []
    for value in values:
        if value is None or not math.isfinite(value):
            out.append(0.0)
        elif hi == lo:
            out.append(0.5)
        else:
            scaled = (value - lo) / (hi - lo)
            out.append(scaled if higher_is_better else 1.0 - scaled)
    return out


def _finite(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _number(value: object) -> float:
    finite = _finite(value)
    return finite if finite is not None else -math.inf
