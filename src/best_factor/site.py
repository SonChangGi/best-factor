"""Static-site JSON exporter for the Best Factor dashboard."""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Iterable

from .io_utils import read_csv_dicts, write_json
from .schemas import CAVEATS, HOLDING_COLUMNS, METRIC_COLUMNS, RANKING_COLUMNS

SCHEMA_VERSION = 1
STATIC_DATA_WARNING = "Static snapshot generated from a prior run; not live market data or investment advice."
UPDATE_AUTOMATION = {
    "timezone": "Asia/Seoul",
    "primary_refresh_kst": "09:00",
    "fallback_refresh_kst": ["10:00", "12:00", "15:00", "18:00"],
    "fallback_policy": "10:00/12:00/15:00/18:00 KST scheduled checks rerun only when the deployed JSON is missing, not generated today in KST, or data_end_date is older than the latest expected US regular session.",
    "manual_update_method": "GitHub Actions workflow_dispatch",
    "manual_update_note": "Static GitHub Pages cannot run Python in the browser; the button opens the authorized GitHub Actions workflow run page.",
}

RANKING_NUMERIC_COLUMNS = set(RANKING_COLUMNS) - {"factor"}
METRIC_NUMERIC_COLUMNS = set(METRIC_COLUMNS) - {"factor"}
HOLDING_NUMERIC_COLUMNS = {"weight", "score"}
SKIPPED_NUMERIC_COLUMNS = {"count"}
INTEGER_COLUMNS = {
    "rank",
    "count",
    "tested_factor_count",
    "effective_factor_count",
    "ranking_count",
    "holding_count",
    "factor_library_size",
    "selected_factor_count",
}
CORE_ARTIFACTS = ("factor_rankings.csv", "factor_metrics.csv", "run_metadata.json")
SAFE_SOURCE_KINDS = {"csv", "yfinance"}
PUBLIC_METADATA_KEYS = {
    "provider",
    "provider_version",
    "price_adjustment",
    "fetched_at",
    "universe_as_of_date",
    "tested_factor_count",
    "effective_factor_count",
    "factor_preset",
    "requested_factor_preset",
    "factor_library_size",
    "selected_factor_count",
    "factor_category_counts",
    "factor_kind_counts",
    "factor_family_summary",
    "skip_resolution_note",
    "factor_library_note",
    "holdout_validation",
    "timing_convention",
    "source_hash",
    "ranking_formula",
    "universe_name",
    "universe_ticker_count",
    "price_ticker_count",
    "universe_scope_note",
    "data_start_date",
    "data_end_date",
    "universe_is_point_in_time",
    "market_cap_filter_basis",
    "market_cap_filter_attempted",
    "market_cap_filter_effective",
    "filter_fallback_reason",
    "current_screen_note",
    "coverage_denominator",
    "requested_tickers",
    "succeeded_tickers",
    "failed_tickers",
}


def build_site_payload(
    run_dir: str | Path,
    *,
    data_scope: str = "csv_run",
    generated_at: str | None = None,
) -> dict[str, object]:
    """Build the versioned JSON payload consumed by ``docs/app.js``.

    Core artifacts must exist. Optional holdings/diagnostics files degrade to
    empty arrays so a partially useful dashboard can still be rendered.
    """
    root = Path(run_dir)
    if not root.exists():
        raise FileNotFoundError(f"run directory not found: {root}")
    _require_core_artifacts(root)

    rankings = _coerce_rows(read_csv_dicts(root / "factor_rankings.csv"), RANKING_NUMERIC_COLUMNS)
    metrics = _coerce_rows(read_csv_dicts(root / "factor_metrics.csv"), METRIC_NUMERIC_COLUMNS)
    latest_holdings = _read_optional_rows(root / "latest_holdings.csv", HOLDING_NUMERIC_COLUMNS)
    skipped_reasons = _read_optional_rows(root / "skipped_reasons.csv", SKIPPED_NUMERIC_COLUMNS)
    holdout_rankings = _read_optional_rows(root / "factor_holdout_rankings.csv", RANKING_NUMERIC_COLUMNS)
    holdout_metrics = _read_optional_rows(root / "factor_holdout_metrics.csv", METRIC_NUMERIC_COLUMNS)
    metadata = _read_metadata(root / "run_metadata.json")
    caveats = metadata.get("caveats") if isinstance(metadata.get("caveats"), list) else CAVEATS
    public_metadata = _public_metadata(metadata)
    best = rankings[0] if rankings else {}
    factor_catalog = metadata.get("factor_catalog") if isinstance(metadata.get("factor_catalog"), list) else []
    factor_family_summary = metadata.get("factor_family_summary") if isinstance(metadata.get("factor_family_summary"), list) else []

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or _utc_now(),
        "data_scope": data_scope,
        "summary": {
            "best_factor": best.get("factor"),
            "best_composite_score": best.get("composite_score"),
            "ranking_count": len(rankings),
            "holding_count": len(latest_holdings),
            "tested_factor_count": _int_or_none(metadata.get("tested_factor_count")),
            "effective_factor_count": _int_or_none(metadata.get("effective_factor_count")),
            "factor_preset": metadata.get("factor_preset") or None,
            "factor_library_size": _int_or_none(metadata.get("factor_library_size")),
            "selected_factor_count": _int_or_none(metadata.get("selected_factor_count")),
            "provider": metadata.get("provider", "unknown"),
            "fetched_at": metadata.get("fetched_at") or None,
            "data_end_date": metadata.get("data_end_date") or None,
            "source_hash": metadata.get("source_hash") or None,
            "universe_as_of_date": metadata.get("universe_as_of_date") or None,
            "static_data_warning": STATIC_DATA_WARNING,
            "interpretation_label": "in_sample_exploratory_with_recent_holdout_check",
            "best_factor_holdout_rank": _holdout_value(metadata, "best_factor_holdout_rank"),
            "best_factor_holdout_cagr": _holdout_value(metadata, "best_factor_holdout_cagr"),
            "best_factor_holdout_sharpe": _holdout_value(metadata, "best_factor_holdout_sharpe"),
        },
        "rankings": rankings,
        "metrics": metrics,
        "latest_holdings": latest_holdings,
        "skipped_reasons": skipped_reasons,
        "holdout_rankings": holdout_rankings,
        "holdout_metrics": holdout_metrics,
        "factor_catalog": factor_catalog,
        "factor_family_summary": factor_family_summary,
        "metadata": public_metadata,
        "automation": UPDATE_AUTOMATION,
        "caveats": [str(c) for c in caveats],
    }
    return payload


def _holdout_value(metadata: dict[str, object], key: str) -> object | None:
    validation = metadata.get("holdout_validation")
    if isinstance(validation, dict):
        return validation.get(key)
    return None


def write_site_payload(
    run_dir: str | Path,
    output_file: str | Path,
    *,
    data_scope: str = "csv_run",
    generated_at: str | None = None,
) -> dict[str, object]:
    """Write dashboard JSON and return the payload."""
    payload = build_site_payload(run_dir, data_scope=data_scope, generated_at=generated_at)
    write_json(output_file, payload)
    return payload


def _require_core_artifacts(root: Path) -> None:
    missing = [name for name in CORE_ARTIFACTS if not (root / name).exists()]
    if missing:
        raise FileNotFoundError(f"missing core run artifact(s): {', '.join(missing)}")


def _public_metadata(metadata: dict[str, object]) -> dict[str, object]:
    public = {key: metadata[key] for key in PUBLIC_METADATA_KEYS if key in metadata and metadata[key] not in (None, "")}
    public["source_kind"] = _safe_source_kind(metadata)
    return public


def _safe_source_kind(metadata: dict[str, object]) -> str:
    provider = str(metadata.get("provider") or "").strip().lower()
    if provider in SAFE_SOURCE_KINDS:
        return provider
    source = str(metadata.get("source") or "").strip()
    if ":" in source:
        prefix = source.split(":", 1)[0].strip().lower()
        if prefix in SAFE_SOURCE_KINDS:
            return prefix
    return "unknown"


def _read_metadata(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid metadata JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"metadata JSON must be an object: {path}")
    return payload


def _read_optional_rows(path: Path, numeric_columns: set[str]) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return _coerce_rows(read_csv_dicts(path), numeric_columns)


def _coerce_rows(rows: Iterable[dict[str, str]], numeric_columns: set[str]) -> list[dict[str, object]]:
    coerced: list[dict[str, object]] = []
    for row in rows:
        out: dict[str, object] = {}
        for key, value in row.items():
            if key in numeric_columns:
                out[key] = _coerce_number(value, integer=key in INTEGER_COLUMNS)
            else:
                out[key] = value
        coerced.append(out)
    return coerced


def _coerce_number(value: object, *, integer: bool = False) -> int | float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).strip())
    except ValueError:
        return None
    if not math.isfinite(number):
        return None
    if integer:
        return int(number)
    return number


def _int_or_none(value: object) -> int | None:
    coerced = _coerce_number(value, integer=True)
    return coerced if isinstance(coerced, int) else None


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
