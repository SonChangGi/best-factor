"""Factor scoring using only data available through each signal date."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .data import group_prices


@dataclass(frozen=True)
class FactorDefinition:
    name: str
    description: str
    requires_fundamentals: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()


DEFAULT_FACTORS = [
    FactorDefinition("momentum_12_1", "12-1 month price momentum"),
    FactorDefinition("momentum_6m", "6 month price momentum skipping the latest month"),
    FactorDefinition("low_volatility", "Negative realized volatility over 6 months"),
    FactorDefinition("short_reversal", "Negative 1 month return"),
    FactorDefinition("risk_adjusted_momentum", "6 month momentum divided by volatility"),
    FactorDefinition("liquidity", "Average dollar volume over 3 months"),
    FactorDefinition("value_pe", "Lower trailing PE is better", ("pe_ratio",)),
    FactorDefinition("quality_roe", "Higher return on equity is better", ("return_on_equity",)),
    FactorDefinition("composite_defensive", "Average rank blend of momentum, low volatility and liquidity", dependencies=("momentum_6m", "low_volatility", "liquidity")),
]

FACTOR_REGISTRY = {f.name: f for f in DEFAULT_FACTORS}


def validate_factor_names(factor_names: Iterable[str]) -> list[str]:
    requested = list(dict.fromkeys(factor_names))
    unknown = [name for name in requested if name not in FACTOR_REGISTRY]
    if unknown:
        raise ValueError(f"unknown factor(s): {', '.join(unknown)}")
    return requested


def expand_factor_dependencies(factor_names: Iterable[str]) -> list[str]:
    requested = validate_factor_names(factor_names)
    expanded: list[str] = []

    def add_with_deps(name: str) -> None:
        for dep in FACTOR_REGISTRY[name].dependencies:
            add_with_deps(dep)
        if name not in expanded:
            expanded.append(name)

    for name in requested:
        add_with_deps(name)
    return expanded


def compute_factor_scores(
    prices: list[dict[str, object]],
    signal_dates: list[object],
    fundamentals: dict[str, list[dict[str, object]]] | None = None,
    factor_names: Iterable[str] | None = None,
    emit_factor_names: Iterable[str] | None = None,
) -> list[dict[str, object]]:
    grouped = group_prices(prices)
    fundamentals = fundamentals or {}
    selected = expand_factor_dependencies(factor_names or [f.name for f in DEFAULT_FACTORS])
    emit = set(emit_factor_names or selected)
    definitions = [FACTOR_REGISTRY[name] for name in selected]
    raw_by_date_factor: dict[tuple[object, str], list[dict[str, object]]] = defaultdict(list)

    for signal_date in signal_dates:
        for factor in definitions:
            if factor.name == "composite_defensive":
                continue
            for ticker, rows in grouped.items():
                point_in_time = _fundamentals_asof(fundamentals.get(ticker, []), signal_date)
                score, reason = _score_factor(factor.name, rows, signal_date, point_in_time)
                raw_by_date_factor[(signal_date, factor.name)].append(
                    _score_row(factor.name, ticker, signal_date, score, reason)
                )

    if "composite_defensive" in selected:
        for signal_date in signal_dates:
            base_names = FACTOR_REGISTRY["composite_defensive"].dependencies
            normalized: dict[str, list[float]] = defaultdict(list)
            for name in base_names:
                rows = raw_by_date_factor.get((signal_date, name), [])
                scores = [float(r["score"]) for r in rows if r["eligible"]]
                by_ticker = {str(r["ticker"]): float(r["score"]) for r in rows if r["eligible"]}
                for ticker, value in by_ticker.items():
                    normalized[ticker].append(_normalize_value(value, scores))
            for ticker in grouped:
                vals = normalized.get(ticker, [])
                if len(vals) == len(base_names):
                    raw_by_date_factor[(signal_date, "composite_defensive")].append(
                        _score_row("composite_defensive", ticker, signal_date, sum(vals) / len(vals), "")
                    )
                else:
                    raw_by_date_factor[(signal_date, "composite_defensive")].append(
                        _score_row("composite_defensive", ticker, signal_date, math.nan, "insufficient_history")
                    )

    scored: list[dict[str, object]] = []
    for key in sorted(raw_by_date_factor, key=lambda k: (str(k[0]), k[1])):
        signal_date, factor_name = key
        if factor_name not in emit:
            continue
        rows = raw_by_date_factor[key]
        eligible_rows = sorted(
            [r for r in rows if r["eligible"]],
            key=lambda r: (-float(r["score"]), str(r["ticker"])),
        )
        rank_by_ticker = {str(r["ticker"]): idx + 1 for idx, r in enumerate(eligible_rows)}
        for row in sorted(rows, key=lambda r: str(r["ticker"])):
            row = dict(row)
            row["rank"] = rank_by_ticker.get(str(row["ticker"]), "")
            scored.append(row)
    return scored


def rows_for_factor_date(scores: list[dict[str, object]], factor: str, signal_date: object) -> list[dict[str, object]]:
    return [r for r in scores if r["factor"] == factor and r["signal_date"] == signal_date]


def factor_names(scores: list[dict[str, object]]) -> list[str]:
    return sorted({str(r["factor"]) for r in scores})


def serialize_factor_scores(scores: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    output = []
    for row in scores:
        signal = row.get("signal_date")
        output.append(
            {
                **row,
                "signal_date": signal.isoformat() if hasattr(signal, "isoformat") else signal,
                "eligible": str(bool(row.get("eligible"))).lower(),
            }
        )
    return output


def _fundamentals_asof(records: list[dict[str, object]], signal_date: object) -> dict[str, float] | None:
    eligible = [r for r in records if r.get("available_at") is not None and r["available_at"] <= signal_date]
    if not eligible:
        return None
    latest = max(eligible, key=lambda r: (r["available_at"], r.get("as_of_date") or r["available_at"]))
    return {k: float(v) for k, v in latest.items() if isinstance(v, (int, float)) and math.isfinite(float(v))}


def _score_factor(name: str, rows: list[dict[str, object]], signal_date: object, fundamentals: dict[str, float] | None) -> tuple[float, str]:
    closes = [(r["date"], float(r["adj_close"])) for r in rows if r["date"] <= signal_date]
    volumes = [(r["date"], float(r.get("volume", 0) or 0), float(r["adj_close"])) for r in rows if r["date"] <= signal_date]
    if name == "momentum_12_1":
        return _momentum(closes, lookback=252, skip=21)
    if name == "momentum_6m":
        return _momentum(closes, lookback=126, skip=21)
    if name == "low_volatility":
        returns = _returns(closes[-127:])
        if len(returns) < 63:
            return math.nan, "insufficient_history"
        vol = statistics.pstdev(returns)
        return -vol, ""
    if name == "short_reversal":
        if len(closes) < 22:
            return math.nan, "insufficient_history"
        return -(closes[-1][1] / closes[-22][1] - 1.0), ""
    if name == "risk_adjusted_momentum":
        mom, reason = _momentum(closes, lookback=126, skip=21)
        if reason:
            return mom, reason
        returns = _returns(closes[-127:])
        vol = statistics.pstdev(returns) if len(returns) >= 2 else 0.0
        if vol <= 0:
            return math.nan, "insufficient_history"
        return mom / vol, ""
    if name == "liquidity":
        if len(volumes) < 63:
            return math.nan, "insufficient_history"
        dollar = [volume * close for _, volume, close in volumes[-63:]]
        return sum(dollar) / len(dollar), ""
    if name == "value_pe":
        if not fundamentals or math.isnan(float(fundamentals.get("pe_ratio", math.nan))):
            return math.nan, "missing_fundamentals"
        pe = float(fundamentals["pe_ratio"])
        if pe <= 0:
            return math.nan, "missing_fundamentals"
        return -pe, ""
    if name == "quality_roe":
        if not fundamentals or math.isnan(float(fundamentals.get("return_on_equity", math.nan))):
            return math.nan, "missing_fundamentals"
        return float(fundamentals["return_on_equity"]), ""
    return math.nan, "provider_error"


def _momentum(closes: list[tuple[object, float]], lookback: int, skip: int) -> tuple[float, str]:
    if len(closes) <= lookback:
        return math.nan, "insufficient_history"
    end_index = len(closes) - 1 - skip
    start_index = len(closes) - 1 - lookback
    if end_index <= start_index or start_index < 0:
        return math.nan, "insufficient_history"
    start = closes[start_index][1]
    end = closes[end_index][1]
    if start <= 0:
        return math.nan, "insufficient_history"
    return end / start - 1.0, ""


def _returns(closes: list[tuple[object, float]]) -> list[float]:
    out = []
    for (_, prev), (_, current) in zip(closes, closes[1:]):
        if prev > 0:
            out.append(current / prev - 1.0)
    return out


def _score_row(factor: str, ticker: str, signal_date: object, score: float, reason: str) -> dict[str, object]:
    eligible = not reason and not math.isnan(score) and math.isfinite(score)
    return {
        "factor": factor,
        "ticker": ticker,
        "signal_date": signal_date,
        "score": score if eligible else math.nan,
        "rank": "",
        "eligible": eligible,
        "skip_reason": "" if eligible else reason or "provider_error",
    }


def _normalize_value(value: float, values: list[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    if not finite or not math.isfinite(value):
        return 0.0
    lo = min(finite)
    hi = max(finite)
    if hi == lo:
        return 0.5
    return (value - lo) / (hi - lo)
