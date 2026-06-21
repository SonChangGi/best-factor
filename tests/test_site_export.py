import csv
import json
import re
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from best_factor.cli import _source_hash_for_run
from best_factor.site import build_public_summary, build_site_payload, write_site_payload


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
            _write_csv(
                run_dir / "portfolio_returns.csv",
                [
                    {
                        "factor": '<script>alert("factor")</script>',
                        "period_start": "2026-04-30",
                        "period_end": "2026-05-29",
                        "return": "0.04",
                        "turnover": "0.30",
                        "holdings_count": "3",
                        "skip_reason": "",
                    }
                ],
            )
            _write_csv(
                run_dir / "benchmark_returns.csv",
                [
                    {
                        "benchmark": "Nasdaq Composite",
                        "ticker": "^IXIC",
                        "period_start": "2026-04-30",
                        "period_end": "2026-05-29",
                        "return": "0.03",
                        "price_date_start": "2026-04-30",
                        "price_date_end": "2026-05-29",
                        "skip_reason": "",
                    }
                ],
            )
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
                        "market_cap_filter_status": "not_applied_metadata_insufficient; dashboard scope is current common-stock plus liquidity, not a large-cap screen",
                        "filter_fallback_reason": "market_cap_metadata_insufficient_preflight",
                        "current_screen_note": "Current screen, not PIT.",
                        "coverage_denominator": "emitted_portfolio_return_periods_per_factor_including_zero_holding_attempts",
                        "transaction_cost_bps": 5.0,
                        "transaction_cost_model": "one_way_notional",
                        "transaction_cost_note": "Transaction-cost bps are charged on one-way traded notional.",
                        "latest_portfolio_holding_count": 20,
                        "latest_portfolio_effective_holdings": 13.5,
                        "latest_portfolio_max_weight": 0.14,
                        "latest_portfolio_top5_weight": 0.47,
                        "latest_portfolio_adv_window": 63,
                        "latest_portfolio_min_adv": 75000000.0,
                        "latest_portfolio_min_adv_ticker": "AAA",
                        "latest_portfolio_weighted_adv": 950000000.0,
                        "latest_portfolio_capacity_5pct_adv": 26785714.29,
                        "latest_portfolio_capacity_10pct_adv": 53571428.57,
                        "latest_portfolio_capacity_limit_ticker": "AAA",
                        "latest_portfolio_average_turnover": 0.58,
                        "latest_portfolio_latest_turnover": 0.42,
                        "latest_portfolio_capacity_note": "Rough capacity uses ADV and is not an order-book model.",
                        "requested_ticker_count": 750,
                        "price_ticker_count": 720,
                        "active_priced_stock_count": 720,
                        "history_qualified_ticker_count": 710,
                        "liquidity_qualified_ticker_count": 705,
                        "latest_factor_eligible_ticker_count": 700,
                        "min_factor_eligible_tickers": 500,
                        "min_history_observations": 252,
                        "eligibility_adv_window": 63,
                        "eligibility_min_dollar_volume": 50000000.0,
                        "factor_eligibility_signal_date": "2026-05-29",
                        "rebalance_eligible_min_count": 640,
                        "rebalance_eligible_median_count": 690.5,
                        "rebalance_eligible_latest_count": 700,
                        "rebalance_history_qualified_latest_count": 710,
                        "rebalance_liquidity_qualified_latest_count": 705,
                        "factor_eligibility_note": "Latest active priced stocks that meet the configured trailing-history observation floor and liquidity floor.",
                        "min_price_tickers": 500,
                        "min_price_coverage_ratio": 0.9,
                        "min_latest_data_coverage_ratio": 0.9,
                        "price_coverage_ratio": 0.96,
                        "latest_data_ticker_count": 715,
                        "latest_data_coverage_ratio": 0.993,
                        "latest_data_reference_date": "2026-05-29",
                        "latest_data_max_date": "2026-06-01",
                        "latest_data_max_date_ticker_count": 100,
                        "latest_data_reference_note": "Latest stock price date with enough ticker coverage under the configured latest-data gate.",
                        "rankable_stock_universe_count": 718,
                        "failed_price_ticker_count": 30,
                        "price_download_chunk_size": 100,
                        "price_download_chunk_count": 8,
                        "price_download_yfinance_chunk_count": 8,
                        "price_download_yahoo_chart_request_count": 3,
                        "price_download_success_rate": 0.96,
                        "provider_order": ["yfinance", "yahoo_chart"],
                        "provider_attempted_sources": ["yfinance", "yahoo_chart"],
                        "provider_fill_counts": {"yfinance": 717, "yahoo_chart": 3},
                        "provider_failed_tickers_by_source": {"yfinance": ["AAA"], "yahoo_chart": []},
                        "provider_error_count": 1,
                        "provider_limitations": "Free Yahoo-family sources only.",
                        "fallback_source": "yahoo_chart",
                        "fallback_filled_ticker_count": 3,
                        "fallback_filled_tickers": ["AAA", "BBB", "CCC"],
                        "factor_scores_archive": "skipped_for_large_live_run",
                        "universe_build_common_stock_candidate_count": 3740,
                        "universe_build_excluded_symbol_counts": {"etf": 1200},
                        "rebalance_frequency": "M",
                        "benchmark_tickers": ["^IXIC"],
                        "benchmark_label": "Nasdaq Composite",
                        "benchmark_return_count": 1,
                        "benchmark_succeeded_tickers": ["^IXIC"],
                        "benchmark_failed_tickers": [],
                        "benchmark_note": "Nasdaq benchmark is a non-investable index comparator; proxy fallbacks are explicit.",
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
        public_summary = build_public_summary(payload)
        self.assertEqual(public_summary["contract"], "quant-research-summary")
        self.assertEqual(public_summary["projectId"], "best")
        self.assertTrue(public_summary["primaryEntities"])
        self.assertTrue(any("not executable trade instructions" in item for item in public_summary["limitations"]))
        self.assertEqual(payload["automation"]["timezone"], "Asia/Seoul")
        self.assertEqual(payload["automation"]["primary_refresh_kst"], "manual")
        self.assertEqual(payload["automation"]["fallback_refresh_kst"], [])
        self.assertIn("workflow_dispatch", payload["automation"]["manual_update_method"])
        self.assertIsInstance(payload["rankings"][0]["rank"], int)
        self.assertIsInstance(payload["rankings"][0]["cagr"], float)
        self.assertIsNone(payload["rankings"][0]["volatility"])
        self.assertEqual(payload["rankings"][0]["unknown_numeric"], "12345")
        self.assertIsNone(payload["metrics"][0]["sortino"])
        self.assertEqual(payload["skipped_reasons"][0]["count"], 2)
        self.assertEqual(payload["latest_holdings"][0]["weight"], 0.5)
        self.assertEqual(payload["factor_period_returns"][0]["return"], 0.04)
        self.assertEqual(payload["factor_period_returns"][0]["holdings_count"], 3)
        self.assertEqual(payload["benchmark_returns"][0]["return"], 0.03)
        self.assertEqual(payload["benchmark_returns"][0]["benchmark"], "Nasdaq Composite")
        self.assertEqual(payload["metadata"]["source_kind"], "csv")
        self.assertFalse(payload["metadata"]["universe_is_point_in_time"])
        self.assertEqual(payload["metadata"]["universe_scope_note"], "Curated current ticker set, not the whole market.")
        self.assertEqual(payload["metadata"]["market_cap_filter_basis"], "current_yfinance_metadata_screen_not_point_in_time")
        self.assertTrue(payload["metadata"]["market_cap_filter_attempted"])
        self.assertFalse(payload["metadata"]["market_cap_filter_effective"])
        self.assertIn("current common-stock plus liquidity", payload["metadata"]["market_cap_filter_status"])
        self.assertEqual(payload["metadata"]["filter_fallback_reason"], "market_cap_metadata_insufficient_preflight")
        self.assertEqual(payload["metadata"]["current_screen_note"], "Current screen, not PIT.")
        self.assertIn("zero_holding", payload["metadata"]["coverage_denominator"])
        self.assertEqual(payload["metadata"]["transaction_cost_bps"], 5.0)
        self.assertEqual(payload["metadata"]["transaction_cost_model"], "one_way_notional")
        self.assertIn("one-way traded notional", payload["metadata"]["transaction_cost_note"])
        self.assertEqual(payload["metadata"]["latest_portfolio_holding_count"], 20)
        self.assertEqual(payload["metadata"]["latest_portfolio_effective_holdings"], 13.5)
        self.assertEqual(payload["metadata"]["latest_portfolio_max_weight"], 0.14)
        self.assertEqual(payload["metadata"]["latest_portfolio_top5_weight"], 0.47)
        self.assertEqual(payload["metadata"]["latest_portfolio_adv_window"], 63)
        self.assertEqual(payload["metadata"]["latest_portfolio_min_adv"], 75000000.0)
        self.assertEqual(payload["metadata"]["latest_portfolio_min_adv_ticker"], "AAA")
        self.assertEqual(payload["metadata"]["latest_portfolio_weighted_adv"], 950000000.0)
        self.assertEqual(payload["metadata"]["latest_portfolio_capacity_10pct_adv"], 53571428.57)
        self.assertEqual(payload["metadata"]["latest_portfolio_capacity_limit_ticker"], "AAA")
        self.assertEqual(payload["metadata"]["latest_portfolio_average_turnover"], 0.58)
        self.assertIn("order-book", payload["metadata"]["latest_portfolio_capacity_note"])
        self.assertEqual(payload["metadata"]["requested_ticker_count"], 750)
        self.assertEqual(payload["metadata"]["price_ticker_count"], 720)
        self.assertEqual(payload["metadata"]["active_priced_stock_count"], 720)
        self.assertEqual(payload["metadata"]["history_qualified_ticker_count"], 710)
        self.assertEqual(payload["metadata"]["liquidity_qualified_ticker_count"], 705)
        self.assertEqual(payload["metadata"]["latest_factor_eligible_ticker_count"], 700)
        self.assertEqual(payload["metadata"]["min_factor_eligible_tickers"], 500)
        self.assertEqual(payload["metadata"]["min_history_observations"], 252)
        self.assertEqual(payload["metadata"]["eligibility_adv_window"], 63)
        self.assertEqual(payload["metadata"]["eligibility_min_dollar_volume"], 50000000.0)
        self.assertEqual(payload["metadata"]["rebalance_eligible_min_count"], 640)
        self.assertEqual(payload["metadata"]["rebalance_eligible_median_count"], 690.5)
        self.assertEqual(payload["metadata"]["rebalance_eligible_latest_count"], 700)
        self.assertEqual(payload["metadata"]["min_price_tickers"], 500)
        self.assertAlmostEqual(payload["metadata"]["min_price_coverage_ratio"], 0.9)
        self.assertAlmostEqual(payload["metadata"]["min_latest_data_coverage_ratio"], 0.9)
        self.assertAlmostEqual(payload["metadata"]["price_coverage_ratio"], 0.96)
        self.assertAlmostEqual(payload["metadata"]["latest_data_coverage_ratio"], 0.993)
        self.assertEqual(payload["metadata"]["latest_data_reference_date"], "2026-05-29")
        self.assertEqual(payload["metadata"]["latest_data_max_date"], "2026-06-01")
        self.assertEqual(payload["metadata"]["latest_data_max_date_ticker_count"], 100)
        self.assertIn("configured latest-data gate", payload["metadata"]["latest_data_reference_note"])
        self.assertEqual(payload["metadata"]["rankable_stock_universe_count"], 718)
        self.assertEqual(payload["metadata"]["price_download_chunk_size"], 100)
        self.assertEqual(payload["metadata"]["price_download_chunk_count"], 8)
        self.assertEqual(payload["metadata"]["price_download_yfinance_chunk_count"], 8)
        self.assertEqual(payload["metadata"]["price_download_yahoo_chart_request_count"], 3)
        self.assertEqual(payload["metadata"]["provider_order"], ["yfinance", "yahoo_chart"])
        self.assertEqual(payload["metadata"]["provider_attempted_sources"], ["yfinance", "yahoo_chart"])
        self.assertEqual(payload["metadata"]["provider_fill_counts"], {"yfinance": 717, "yahoo_chart": 3})
        self.assertEqual(payload["metadata"]["provider_failed_tickers_by_source"], {"yfinance": ["AAA"], "yahoo_chart": []})
        self.assertEqual(payload["metadata"]["provider_error_count"], 1)
        self.assertEqual(payload["metadata"]["fallback_source"], "yahoo_chart")
        self.assertEqual(payload["metadata"]["fallback_filled_ticker_count"], 3)
        self.assertEqual(payload["metadata"]["fallback_filled_tickers"], ["AAA", "BBB", "CCC"])
        self.assertEqual(payload["metadata"]["factor_scores_archive"], "skipped_for_large_live_run")
        self.assertEqual(payload["metadata"]["universe_build_common_stock_candidate_count"], 3740)
        self.assertEqual(payload["metadata"]["universe_build_excluded_symbol_counts"], {"etf": 1200})
        self.assertEqual(payload["metadata"]["rebalance_frequency"], "M")
        self.assertEqual(payload["metadata"]["benchmark_tickers"], ["^IXIC"])
        self.assertEqual(payload["metadata"]["benchmark_return_count"], 1)
        self.assertIn("proxy fallbacks", payload["metadata"]["benchmark_note"])
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
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _minimal_core(run_dir, metadata={"provider": "yfinance_yahoo_chart", "source": "internal"})
            by_resilient_provider = build_site_payload(run_dir, generated_at="2026-06-10T01:02:03Z")
        self.assertEqual(by_resilient_provider["metadata"]["source_kind"], "yfinance_yahoo_chart")

    def test_no_source_files_have_no_source_hash(self):
        args = Namespace(prices_file=None, universe_file=None, fundamentals_file=None)
        self.assertIsNone(_source_hash_for_run(args))

    def test_optional_artifacts_can_be_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            _minimal_core(run_dir)
            payload = build_site_payload(run_dir, generated_at="2026-06-10T01:02:03Z")
        self.assertEqual(payload["latest_holdings"], [])
        self.assertEqual(payload["factor_period_returns"], [])
        self.assertEqual(payload["benchmark_returns"], [])
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
            summary = json.loads((out.parent / "summary.json").read_text())
        self.assertEqual(loaded["schema_version"], 1)
        self.assertEqual(summary["contract"], "quant-research-summary")
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
