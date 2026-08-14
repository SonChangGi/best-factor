#!/usr/bin/env python3
"""Build bounded Control API callback documents from verified Best Factor outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit


SUMMARY_ALLOWLIST = (
    "best_composite_score",
    "best_factor",
    "best_factor_holdout_cagr",
    "best_factor_holdout_rank",
    "best_factor_holdout_sharpe",
    "data_end_date",
    "effective_factor_count",
    "factor_library_size",
    "factor_preset",
    "fetched_at",
    "holding_count",
    "interpretation_label",
    "provider",
    "ranking_count",
    "selected_factor_count",
    "source_hash",
    "tested_factor_count",
    "universe_as_of_date",
)


def _require_environment(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "")
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def validate_callback_base(value: str) -> None:
    callback_base = urlsplit(value)
    if (
        callback_base.scheme != "https"
        or not callback_base.hostname
        or callback_base.username
        or callback_base.password
        or callback_base.query
        or callback_base.fragment
    ):
        raise SystemExit(
            "Control callback URL must be an HTTPS base without credentials, query, or fragment"
        )


def _read_object(path: Path, *, label: str) -> dict[str, object]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"{label} is unavailable or invalid JSON") from exc
    if not isinstance(document, dict):
        raise SystemExit(f"{label} must be an object")
    return document


def _binding(environment: Mapping[str, str]) -> dict[str, str]:
    return {
        "projectId": "best-factor",
        "runId": _require_environment(environment, "CONTROL_RUN_ID"),
        "inputSchemaVersion": _require_environment(
            environment, "CONTROL_INPUT_SCHEMA_VERSION"
        ),
        "inputSchemaHash": _require_environment(
            environment, "CONTROL_INPUT_SCHEMA_HASH"
        ),
        "configHashAlgorithm": _require_environment(
            environment, "CONTROL_CONFIG_HASH_ALGORITHM"
        ),
        "configHash": _require_environment(environment, "CONTROL_CONFIG_HASH"),
    }


def build_result_manifest(
    result_path: Path,
    config_path: Path,
    *,
    environment: Mapping[str, str] = os.environ,
) -> dict[str, object]:
    validate_callback_base(_require_environment(environment, "QUANT_CONTROL_CALLBACK_URL"))
    result_bytes = result_path.read_bytes()
    payload = _read_object(result_path, label="latest-results")
    config_envelope = _read_object(config_path, label="effective config")
    summary = payload.get("summary")
    metadata = payload.get("metadata")
    if not isinstance(summary, dict):
        raise SystemExit("latest-results summary must be an object")
    if not isinstance(metadata, dict):
        metadata = {}
    requested_inputs = config_envelope.get("config")
    if not isinstance(requested_inputs, dict):
        raise SystemExit("effective config.config must be an object")

    bounded_payload = {
        "schema_version": payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "summary": {key: summary[key] for key in SUMMARY_ALLOWLIST if key in summary},
    }
    bounded_bytes = json.dumps(
        bounded_payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(bounded_bytes) > 64 * 1024:
        raise SystemExit("Best Factor control summary exceeds 64 KiB")

    source = payload.get("data_scope")
    source_hash = summary.get("source_hash") or metadata.get("source_hash")
    data_as_of = summary.get("data_end_date") or metadata.get("data_end_date")
    calculated_at = payload.get("generated_at")
    if not isinstance(source, str) or not source:
        raise SystemExit("latest-results data_scope is required")
    if not isinstance(source_hash, str) or not re.fullmatch(
        r"[0-9a-fA-F]{8,128}", source_hash
    ):
        raise SystemExit(
            "latest-results source hash must be an 8-128 character hexadecimal digest"
        )
    if not isinstance(data_as_of, str) or not data_as_of:
        raise SystemExit("latest-results data end date is required")
    if not isinstance(calculated_at, str) or not calculated_at:
        raise SystemExit("latest-results generated_at is required")

    binding = _binding(environment)
    effective_config_hash = config_envelope.get("config_hash")
    if effective_config_hash != binding["configHash"]:
        raise SystemExit("effective config hash drifted after control binding validation")
    return {
        "binding": binding,
        "requestedInputs": requested_inputs,
        "normalizedInputs": requested_inputs,
        "effectiveConfigHash": effective_config_hash,
        "effectiveInputs": requested_inputs,
        "ignoredInputs": [],
        "fallbacks": [],
        "fallbackUsed": False,
        "fallbackReason": None,
        "dataAsOf": data_as_of,
        "calculatedAt": calculated_at,
        "codeVersion": _require_environment(environment, "CODE_VERSION"),
        "dataIdentity": {
            "source": source,
            "sourceHash": source_hash,
            "dataAsOf": data_as_of,
        },
        "artifact": {
            "url": _require_environment(environment, "ARTIFACT_URL"),
            "sha256": hashlib.sha256(result_bytes).hexdigest(),
            "byteSize": len(result_bytes),
            "contractVersion": "best-factor/latest-results/v1",
        },
        "payload": bounded_payload,
    }


def build_failure_manifest(
    *,
    environment: Mapping[str, str] = os.environ,
    now: datetime | None = None,
) -> dict[str, object]:
    validate_callback_base(_require_environment(environment, "QUANT_CONTROL_CALLBACK_URL"))
    binding = _binding(environment)
    occurred_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "binding": binding,
        "errorCode": "worker_workflow_failed",
        "errorMessage": (
            "Best Factor controlled GitHub Actions job failed before a verified result was published."
        ),
        "providerRunId": f"github-actions:{binding['runId']}",
        "occurredAt": occurred_at.isoformat().replace("+00:00", "Z"),
    }


def _write_compact_json(path: Path, document: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    result = subparsers.add_parser("result")
    result.add_argument("--result-json", type=Path, required=True)
    result.add_argument("--config-json", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    failure = subparsers.add_parser("failure")
    failure.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "result":
        document = build_result_manifest(args.result_json, args.config_json)
    else:
        document = build_failure_manifest()
    _write_compact_json(args.output, document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
