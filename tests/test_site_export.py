import csv
import json
import re
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from best_factor.cli import _source_hash_for_run
from best_factor.site import build_site_payload, write_site_payload


class SiteExportTest(unittest.TestCase):
    def test_build_site_payload_schema_numeric_allowlist_and_freshness(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _write_csv(
                run_dir / "factor_rankings.csv",
                [
                    {
                        "rank": "1",
                        "factor": '<script>alert("factor")</script>',
                        "cagr": "0.12",
                        "annual_return": "0.13",
                        "volatility": "bad",
                        "sharpe": "1.5",
                        "sortino": "2.5",
                        "calmar": "3.5",
                        "max_drawdown": "-0.20",
                        "turnover": "0.10",
                        "coverage": "1",
                        "composite_score": "0.88",
                        "unknown_numeric": "12345",
                    }
                ],
            )
            _write_csv(
                run_dir / "factor_metrics.csv",
                [
                    {
                        "factor": "momentum",
                        "cagr": "0.11",
                        "annual_return": "0.12",
                        "volatility": "0.20",
                        "sharpe": "1.1",
                        "sortino": "",
                        "calmar": "1.7",
                        "max_drawdown": "-0.15",
                        "turnover": "0.2",
                        "coverage": "1",
                        "composite_score": "0.7",
                    }
                ],
            )
            _write_csv(
                run_dir / "latest_holdings.csv",
                [
                    {
                        "rebalance_date": "2026-05-29",
                        "factor": "momentum",
                        "ticker": '<img src=x onerror=alert("x")>',
                        "weight": "0.5",
                        "score": "9.9",
                        "price_date_used": "2026-05-29",
                    }
                ],
            )
            _write_csv(run_dir / "skipped_reasons.csv", [{"skip_reason": "missing", "count": "2"}])
            (run_dir / "run_metadata.json").write_text(
                json.dumps(
                    {
                        "provider": "csv",
                        "fetched_at": "2026-06-10T00:00:00Z",
                        "source": "csv:/Users/example/private/prices.csv",
                        "cache_dir": "/Users/example/.cache/best-factor",
                        "source_hash": "abc123",
                        "universe_scope_note": "Curated current ticker set, not the whole market.",
                        "universe_is_point_in_time": False,
                        "market_cap_filter_basis": "current_yfinance_metadata_screen_not_point_in_time",
                        "market_cap_filter_attempted": True,
                        "market_cap_filter_effective": False,
                        "filter_fallback_reason": "market_cap_metadata_insufficient_preflight",
                        "current_screen_note": "Current screen, not PIT.",
                        "coverage_denominator": "emitted_portfolio_return_periods_per_factor_including_zero_holding_attempts",
                        "tested_factor_count": 2,
                        "effective_factor_count": 1,
                        "factor_preset": "zoo",
                        "requested_factor_preset": "zoo",
                        "factor_library_size": 318,
                        "selected_factor_count": 318,
                        "factor_category_counts": {"momentum": 90, "risk": 25},
                        "factor_kind_counts": {"momentum": 80, "price_volume_corr": 5},
                        "factor_family_summary": [
                            {
                                "category": "accumulation",
                                "description": "Price/volume confirmation.",
                                "count": 5,
                                "kind_counts": {"price_volume_corr": 5},
                                "examples": ["price_volume_corr_63d"],
                                "requires_fundamentals_count": 0,
                            }
                        ],
                        "factor_catalog": [
                            {
                                "name": "price_volume_corr_63d",
                                "description": "Correlation between returns and dollar-volume changes.",
                                "category": "accumulation",
                                "category_description": "Price/volume confirmation.",
                                "kind": "price_volume_corr",
                                "params": {"window": 63},
                                "dependencies": [],
                                "requires_fundamentals": [],
                            }
                        ],
                        "skip_resolution_note": "Actionable skips are recorded by reason.",
                        "factor_library_note": "Best among tested candidates.",
                        "holdout_validation": {
                            "method": "recent_tail_by_factor",
                            "holdout_fraction": 0.25,
                            "min_periods": 6,
                            "best_factor_holdout_rank": 1,
                            "best_factor_holdout_cagr": 0.2,
                            "best_factor_holdout_sharpe": 1.5,
                            "holdout_ranked_factor_count": 1,
                        },
                        "run_config": {"prices_file": "/Users/example/private/prices.csv", "output_dir": "/tmp/private-run"},
                        "caveats": ["Use <care>"],
                    }
                )
            )

            payload = build_site_payload(run_dir, data_scope="fixture_sample", generated_at="2026-06-10T01:02:03Z")

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["generated_at"], "2026-06-10T01:02:03Z")
        self.assertEqual(payload["data_scope"], "fixture_sample")
        self.assertEqual(payload["summary"]["best_factor"], '<script>alert("factor")</script>')
        self.assertEqual(payload["summary"]["source_hash"], "abc123")
        self.assertEqual(payload["summary"]["factor_preset"], "zoo")
        self.assertEqual(payload["summary"]["factor_library_size"], 318)
        self.assertEqual(payload["summary"]["selected_factor_count"], 318)
        self.assertEqual(payload["summary"]["interpretation_label"], "in_sample_exploratory_with_recent_holdout_check")
        self.assertEqual(payload["summary"]["best_factor_holdout_rank"], 1)
        self.assertEqual(payload["summary"]["best_factor_holdout_cagr"], 0.2)
        self.assertIn("not live market data", payload["summary"]["static_data_warning"])
        self.assertEqual(payload["automation"]["timezone"], "Asia/Seoul")
        self.assertEqual(payload["automation"]["primary_refresh_kst"], "09:00")
        self.assertIn("10:00", payload["automation"]["fallback_refresh_kst"])
        self.assertIn("workflow_dispatch", payload["automation"]["manual_update_method"])
        self.assertIsInstance(payload["rankings"][0]["rank"], int)
        self.assertIsInstance(payload["rankings"][0]["cagr"], float)
        self.assertIsNone(payload["rankings"][0]["volatility"])
        self.assertEqual(payload["rankings"][0]["unknown_numeric"], "12345")
        self.assertIsNone(payload["metrics"][0]["sortino"])
        self.assertEqual(payload["skipped_reasons"][0]["count"], 2)
        self.assertEqual(payload["latest_holdings"][0]["weight"], 0.5)
        self.assertEqual(payload["metadata"]["source_kind"], "csv")
        self.assertFalse(payload["metadata"]["universe_is_point_in_time"])
        self.assertEqual(payload["metadata"]["universe_scope_note"], "Curated current ticker set, not the whole market.")
        self.assertEqual(payload["metadata"]["market_cap_filter_basis"], "current_yfinance_metadata_screen_not_point_in_time")
        self.assertTrue(payload["metadata"]["market_cap_filter_attempted"])
        self.assertFalse(payload["metadata"]["market_cap_filter_effective"])
        self.assertEqual(payload["metadata"]["filter_fallback_reason"], "market_cap_metadata_insufficient_preflight")
        self.assertEqual(payload["metadata"]["current_screen_note"], "Current screen, not PIT.")
        self.assertIn("zero_holding", payload["metadata"]["coverage_denominator"])
        self.assertEqual(payload["metadata"]["factor_category_counts"], {"momentum": 90, "risk": 25})
        self.assertEqual(payload["metadata"]["factor_kind_counts"], {"momentum": 80, "price_volume_corr": 5})
        self.assertEqual(payload["factor_family_summary"][0]["category"], "accumulation")
        self.assertEqual(payload["factor_catalog"][0]["name"], "price_volume_corr_63d")
        self.assertEqual(payload["metadata"]["skip_resolution_note"], "Actionable skips are recorded by reason.")
        self.assertEqual(payload["metadata"]["factor_library_note"], "Best among tested candidates.")
        self.assertEqual(payload["metadata"]["holdout_validation"]["best_factor_holdout_rank"], 1)
        self.assertEqual(payload["holdout_rankings"], [])
        self.assertEqual(payload["holdout_metrics"], [])
        self.assertNotIn("source", payload["metadata"])
        self.assertNotIn("run_config", payload["metadata"])
        self.assertNotIn("cache_dir", payload["metadata"])
        self.assertNotIn("/Users/example", json.dumps(payload["metadata"]))

    def test_public_source_kind_never_leaks_raw_paths(self):
        for raw_source in ["/Users/alice/private/prices.csv", r"C:\Users\alice\private\prices.csv"]:
            with self.subTest(raw_source=raw_source):
                with tempfile.TemporaryDirectory() as tmp:
                    run_dir = Path(tmp)
                    _minimal_core(run_dir, metadata={"provider": "custom", "source": raw_source})
                    payload = build_site_payload(run_dir, generated_at="2026-06-10T01:02:03Z")
                self.assertEqual(payload["metadata"]["source_kind"], "unknown")
                self.assertNotIn("alice", json.dumps(payload["metadata"]))
                self.assertNotIn("private", json.dumps(payload["metadata"]))

    def test_public_source_kind_uses_provider_or_safe_scheme(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _minimal_core(run_dir, metadata={"provider": "csv", "source": "/Users/alice/private/prices.csv"})
            by_provider = build_site_payload(run_dir, generated_at="2026-06-10T01:02:03Z")
        self.assertEqual(by_provider["metadata"]["source_kind"], "csv")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _minimal_core(run_dir, metadata={"provider": "custom", "source": "yfinance:AAPL,MSFT"})
            by_scheme = build_site_payload(run_dir, generated_at="2026-06-10T01:02:03Z")
        self.assertEqual(by_scheme["metadata"]["source_kind"], "yfinance")

    def test_no_source_files_have_no_source_hash(self):
        args = Namespace(prices_file=None, universe_file=None, fundamentals_file=None)
        self.assertIsNone(_source_hash_for_run(args))

    def test_optional_artifacts_can_be_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _minimal_core(run_dir)
            payload = build_site_payload(run_dir, generated_at="2026-06-10T01:02:03Z")
        self.assertEqual(payload["latest_holdings"], [])
        self.assertEqual(payload["skipped_reasons"], [])
        self.assertIsNone(payload["summary"]["source_hash"])
        self.assertIsNone(payload["summary"]["fetched_at"])

    def test_missing_core_artifacts_fail_with_useful_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(FileNotFoundError, "factor_rankings.csv"):
                build_site_payload(tmp)

    def test_write_site_payload_outputs_iso_utc_generated_at(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            _minimal_core(run_dir)
            out = Path(tmp) / "site" / "latest-results.json"
            payload = write_site_payload(run_dir, out)
            loaded = json.loads(out.read_text())
        self.assertEqual(loaded["schema_version"], 1)
        self.assertRegex(payload["generated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _minimal_core(run_dir: Path, metadata: dict[str, object] | None = None) -> None:
    _write_csv(
        run_dir / "factor_rankings.csv",
        [
            {
                "rank": "1",
                "factor": "momentum",
                "cagr": "0.1",
                "annual_return": "0.1",
                "volatility": "0.2",
                "sharpe": "1",
                "sortino": "1",
                "calmar": "1",
                "max_drawdown": "-0.1",
                "turnover": "0",
                "coverage": "1",
                "composite_score": "0.5",
            }
        ],
    )
    _write_csv(
        run_dir / "factor_metrics.csv",
        [
            {
                "factor": "momentum",
                "cagr": "0.1",
                "annual_return": "0.1",
                "volatility": "0.2",
                "sharpe": "1",
                "sortino": "1",
                "calmar": "1",
                "max_drawdown": "-0.1",
                "turnover": "0",
                "coverage": "1",
                "composite_score": "0.5",
            }
        ],
    )
    (run_dir / "run_metadata.json").write_text(json.dumps(metadata or {"provider": "csv"}))


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
