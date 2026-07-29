#!/usr/bin/env python3
"""Fail closed unless generated Best Factor public files form one semantic result."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from best_factor.site import build_public_summary
from dashboard_config import (
    build_result_binding,
    load_config,
    validate_public_envelope,
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {value}")
            ),
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"invalid public JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"public JSON must be an object: {path}")
    return payload


def _reject_non_finite(value: Any, *, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite public number at {path}")
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_non_finite(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_non_finite(child, path=f"{path}[{index}]")


def validate_publication(
    *,
    results_path: Path,
    summary_path: Path,
    public_config_path: Path,
    private_config_path: Path,
) -> None:
    results = _load_json(results_path)
    summary = _load_json(summary_path)
    public_config = _load_json(public_config_path)
    for document in (results, summary, public_config):
        _reject_non_finite(document)

    if results.get("schema_version") != 1:
        raise ValueError("latest-results schema_version must be 1")
    rankings = results.get("rankings")
    holdings = results.get("latest_holdings")
    result_summary = results.get("summary")
    if not isinstance(rankings, list) or not rankings:
        raise ValueError("latest-results rankings must be nonempty")
    if not isinstance(holdings, list) or not holdings:
        raise ValueError("latest-results holdings must be nonempty")
    if not isinstance(result_summary, dict):
        raise ValueError("latest-results summary must be an object")
    if result_summary.get("ranking_count") != len(rankings):
        raise ValueError("latest-results ranking_count mismatch")
    if result_summary.get("holding_count") != len(holdings):
        raise ValueError("latest-results holding_count mismatch")
    if result_summary.get("best_factor") != rankings[0].get("factor"):
        raise ValueError("latest-results best_factor/ranking order mismatch")

    expected_summary = build_public_summary(results)
    expected_summary["payload"]["detailBytes"] = results_path.stat().st_size  # type: ignore[index]
    if summary != expected_summary:
        raise ValueError("summary.json is not the exact projection of latest-results.json")

    private_config = load_config(private_config_path)
    public_values, public_binding = validate_public_envelope(public_config)
    if public_values != private_config:
        raise ValueError("public/private dashboard config mismatch")
    if public_binding != build_result_binding(results):
        raise ValueError("dashboard config result binding mismatch")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("docs/data/latest-results.json"))
    parser.add_argument("--summary", type=Path, default=Path("docs/data/summary.json"))
    parser.add_argument(
        "--public-config",
        type=Path,
        default=Path("docs/data/dashboard-config.json"),
    )
    parser.add_argument(
        "--private-config",
        type=Path,
        default=Path(".github/best-factor-dashboard-config.json"),
    )
    args = parser.parse_args()
    validate_publication(
        results_path=args.results,
        summary_path=args.summary,
        public_config_path=args.public_config,
        private_config_path=args.private_config,
    )
    print("best_factor_publication_validation=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
