#!/usr/bin/env python3
"""Validate and persist dashboard orchestration settings without touching analysis code."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
from collections.abc import Mapping
from pathlib import Path

from best_factor.factors import FACTOR_REGISTRY, validate_factor_names

SCHEMA_VERSION = 1
CONFIG_KEYS = (
    "period",
    "rebalance",
    "top_n",
    "weighting",
    "factor_preset",
    "factor_allowlist",
    "min_market_cap",
    "min_dollar_volume",
    "eligibility_adv_window",
    "transaction_cost_bps",
    "transaction_cost_model",
)
DEFAULT_CONFIG: dict[str, object] = {
    "period": "5y",
    "rebalance": "M",
    "top_n": 20,
    "weighting": "score",
    "factor_preset": "zoo",
    "factor_allowlist": [],
    "min_market_cap": 10_000_000_000.0,
    "min_dollar_volume": 50_000_000.0,
    "eligibility_adv_window": 63,
    "transaction_cost_bps": 5.0,
    "transaction_cost_model": "one_way_notional",
}
INPUT_ENV_KEYS = {key: f"INPUT_{key.upper()}" for key in CONFIG_KEYS}
CHOICES = {
    "period": {"2y", "5y", "10y"},
    "rebalance": {"M", "W"},
    "weighting": {"equal", "score"},
    "factor_preset": {"core", "zoo"},
    "transaction_cost_model": {"one_way_notional", "portfolio_turnover"},
}
INTEGER_BOUNDS = {
    "top_n": (1, 100),
    "eligibility_adv_window": (5, 252),
}
NUMBER_BOUNDS = {
    "min_market_cap": (0.0, 1e15),
    "min_dollar_volume": (0.0, 1e15),
    "transaction_cost_bps": (0.0, 1000.0),
}
KEEP_SENTINELS = {"", "keep"}
FACTOR_PRESET_SENTINEL = "__preset__"


def normalize_config(raw: Mapping[str, object], *, require_exact_keys: bool = True) -> dict[str, object]:
    keys = set(raw)
    expected = set(CONFIG_KEYS)
    if require_exact_keys and keys != expected:
        missing = sorted(expected - keys)
        unknown = sorted(keys - expected)
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown: {', '.join(unknown)}")
        raise ValueError(f"dashboard config keys must match the 11-field contract ({'; '.join(details)})")

    values = {**DEFAULT_CONFIG, **dict(raw)}
    normalized: dict[str, object] = {}
    for key in CONFIG_KEYS:
        value = values[key]
        if key in CHOICES:
            normalized[key] = _choice(key, value, CHOICES[key])
        elif key in INTEGER_BOUNDS:
            minimum, maximum = INTEGER_BOUNDS[key]
            normalized[key] = _integer(key, value, minimum=minimum, maximum=maximum)
        elif key in NUMBER_BOUNDS:
            minimum, maximum = NUMBER_BOUNDS[key]
            normalized[key] = _number(key, value, minimum=minimum, maximum=maximum)
        elif key == "factor_allowlist":
            normalized[key] = _factor_allowlist(value)
        else:  # pragma: no cover - CONFIG_KEYS is deliberately exhaustive
            raise AssertionError(f"unhandled dashboard config key: {key}")
    return normalized


def make_envelope(config: Mapping[str, object]) -> dict[str, object]:
    normalized = normalize_config(config)
    return {
        "schema_version": SCHEMA_VERSION,
        "config": normalized,
        "config_hash": config_hash(normalized),
    }


def validate_envelope(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("dashboard config envelope must be a JSON object")
    expected = {"schema_version", "config", "config_hash"}
    if set(payload) != expected:
        raise ValueError("dashboard config envelope keys must be schema_version, config, and config_hash")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported dashboard config schema_version: {payload.get('schema_version')}")
    config = payload.get("config")
    if not isinstance(config, dict):
        raise ValueError("dashboard config envelope config must be an object")
    normalized = normalize_config(config)
    expected_hash = config_hash(normalized)
    if payload.get("config_hash") != expected_hash:
        raise ValueError("dashboard config_hash does not match the canonical config")
    return normalized


def resolve_config(persisted: Mapping[str, object], overrides: Mapping[str, object]) -> dict[str, object]:
    merged = normalize_config(persisted)
    unknown = sorted(set(overrides) - set(CONFIG_KEYS))
    if unknown:
        raise ValueError(f"unknown dashboard override(s): {', '.join(unknown)}")
    for key, value in overrides.items():
        text = str(value).strip() if isinstance(value, str) else None
        if value is None or text in KEEP_SENTINELS:
            continue
        if key == "factor_allowlist" and text == FACTOR_PRESET_SENTINEL:
            merged[key] = []
        else:
            merged[key] = value
    return normalize_config(merged)


def config_hash(config: Mapping[str, object]) -> str:
    canonical = json.dumps(dict(config), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def envelope_bytes(config: Mapping[str, object]) -> bytes:
    return (json.dumps(make_envelope(config), ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def make_public_envelope(config: Mapping[str, object], result_payload: object) -> dict[str, object]:
    envelope = make_envelope(config)
    envelope["result_binding"] = build_result_binding(result_payload)
    return envelope


def public_envelope_bytes(config: Mapping[str, object], result_payload: object) -> bytes:
    payload = make_public_envelope(config, result_payload)
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def build_result_binding(result_payload: object) -> dict[str, str]:
    if not isinstance(result_payload, dict):
        raise ValueError("latest-results JSON must be an object")
    if result_payload.get("schema_version") != 1:
        raise ValueError("latest-results schema_version must be 1")
    generated_at = _required_text(result_payload.get("generated_at"), "latest-results generated_at")
    try:
        parsed_generated_at = dt.datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("latest-results generated_at must be an ISO-8601 timestamp") from exc
    if not generated_at.endswith("Z") or parsed_generated_at.tzinfo is None:
        raise ValueError("latest-results generated_at must be a UTC timestamp ending in Z")

    summary = result_payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("latest-results summary must be an object")
    source_hash = _required_text(summary.get("source_hash"), "latest-results summary.source_hash")
    if not re.fullmatch(r"[A-Fa-f0-9]{8,128}", source_hash):
        raise ValueError("latest-results summary.source_hash must be a hexadecimal digest")
    data_end_date = _required_text(summary.get("data_end_date"), "latest-results summary.data_end_date")
    try:
        dt.date.fromisoformat(data_end_date)
    except ValueError as exc:
        raise ValueError("latest-results summary.data_end_date must be an ISO date") from exc
    return {
        "generated_at": generated_at,
        "source_hash": source_hash,
        "data_end_date": data_end_date,
    }


def validate_public_envelope(payload: object) -> tuple[dict[str, object], dict[str, str]]:
    if not isinstance(payload, dict):
        raise ValueError("public dashboard config envelope must be a JSON object")
    expected = {"schema_version", "config", "config_hash", "result_binding"}
    if set(payload) != expected:
        raise ValueError("public dashboard config envelope must contain only config fields and result_binding")
    private_payload = {key: payload[key] for key in ("schema_version", "config", "config_hash")}
    config = validate_envelope(private_payload)
    binding = payload.get("result_binding")
    if not isinstance(binding, dict) or set(binding) != {"generated_at", "source_hash", "data_end_date"}:
        raise ValueError("result_binding keys must be generated_at, source_hash, and data_end_date")
    synthetic_result = {
        "schema_version": 1,
        "generated_at": binding.get("generated_at"),
        "summary": {
            "source_hash": binding.get("source_hash"),
            "data_end_date": binding.get("data_end_date"),
        },
    }
    return config, build_result_binding(synthetic_result)


def load_config(path: str | Path) -> dict[str, object]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid dashboard config JSON: {source}") from exc
    return validate_envelope(payload)


def input_overrides(environment: Mapping[str, str]) -> dict[str, object]:
    return {key: environment.get(env_key, "") for key, env_key in INPUT_ENV_KEYS.items()}


def write_resolved_outputs(
    config: Mapping[str, object],
    *,
    envelope_output: str | Path,
    values_output: str | Path,
) -> None:
    normalized = normalize_config(config)
    Path(envelope_output).write_bytes(envelope_bytes(normalized))
    values: list[bytes] = []
    for key in CONFIG_KEYS:
        value = normalized[key]
        if key == "factor_allowlist":
            value = ",".join(value)  # type: ignore[arg-type]
        values.append(str(value).encode("utf-8"))
    Path(values_output).write_bytes(b"\0".join(values) + b"\0")


def write_public_output(
    config: Mapping[str, object],
    *,
    result_file: str | Path,
    public_output: str | Path,
) -> None:
    source = Path(result_file)
    try:
        result_payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid latest-results JSON: {source}") from exc
    Path(public_output).write_bytes(public_envelope_bytes(config, result_payload))


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _choice(key: str, value: object, allowed: set[str]) -> str:
    text = str(value).strip()
    if text not in allowed:
        raise ValueError(f"{key} must be one of: {', '.join(sorted(allowed))}")
    return text


def _integer(key: str, value: object, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    if isinstance(value, int):
        number = value
    else:
        text = str(value).strip()
        if not re.fullmatch(r"[+-]?\d+", text):
            raise ValueError(f"{key} must be an integer")
        number = int(text)
    if number < minimum or number > maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return number


def _number(key: str, value: object, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{key} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{key} must be a finite number")
    if number < minimum or number > maximum:
        raise ValueError(f"{key} must be between {minimum:g} and {maximum:g}")
    if number == 0:
        return 0.0
    return number


def _factor_allowlist(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        names = [name for name in re.split(r"[,\s]+", value.strip()) if name]
    elif isinstance(value, list):
        names = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("factor_allowlist entries must be factor names")
            names.extend(name for name in re.split(r"[,\s]+", item.strip()) if name)
    else:
        raise ValueError("factor_allowlist must be a list or comma/space-separated factor names")
    unique = list(dict.fromkeys(names))
    if len(unique) > len(FACTOR_REGISTRY):
        raise ValueError("factor_allowlist exceeds the available factor registry")
    invalid_syntax = [name for name in unique if not re.fullmatch(r"[A-Za-z0-9_]+", name)]
    if invalid_syntax:
        raise ValueError(f"invalid factor name syntax: {', '.join(invalid_syntax)}")
    return validate_factor_names(unique)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persisted", required=True)
    parser.add_argument("--mode", choices=["resolve", "publish"], default="resolve")
    parser.add_argument("--event-name", choices=["workflow_dispatch", "schedule"])
    parser.add_argument("--envelope-output")
    parser.add_argument("--values-output")
    parser.add_argument("--result-file")
    parser.add_argument("--public-output")
    args = parser.parse_args()

    persisted = load_config(args.persisted)
    if args.mode == "publish":
        if not args.result_file or not args.public_output:
            parser.error("--mode publish requires --result-file and --public-output")
        write_public_output(
            persisted,
            result_file=args.result_file,
            public_output=args.public_output,
        )
        print(Path(args.public_output).read_text(encoding="utf-8"), end="")
        return 0

    if not args.event_name or not args.envelope_output or not args.values_output:
        parser.error("--mode resolve requires --event-name, --envelope-output, and --values-output")
    overrides = input_overrides(os.environ) if args.event_name == "workflow_dispatch" else {}
    resolved = resolve_config(persisted, overrides)
    write_resolved_outputs(
        resolved,
        envelope_output=args.envelope_output,
        values_output=args.values_output,
    )
    print(Path(args.envelope_output).read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
