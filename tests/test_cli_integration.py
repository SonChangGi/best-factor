import csv
import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from best_factor import cli as cli_module
from best_factor.data import load_prices_csv
from best_factor.schemas import CAVEATS, HOLDING_COLUMNS, METRIC_COLUMNS, RANKING_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class CliIntegrationTest(unittest.TestCase):
    def run_cli(self, *extra):
        out = tempfile.TemporaryDirectory()
        self.addCleanup(out.cleanup)
        cmd = [
            sys.executable,
            "-m",
            "best_factor.cli",
            "run",
            "--prices-file",
            str(FIXTURES / "prices.csv"),
            "--universe-file",
            str(FIXTURES / "universe.csv"),
            "--fundamentals-file",
            str(FIXTURES / "fundamentals.csv"),
            "--output-dir",
            out.name,
            "--rebalance",
            "M",
            "--top-n",
            "3",
            "--factor-preset",
            "core",
            *extra,
        ]
        completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return Path(out.name)

    def test_offline_cli_writes_expected_artifacts_and_schemas(self):
        out = self.run_cli()
        expected = [
            "factor_metrics.csv",
            "factor_rankings.csv",
            "factor_holdout_metrics.csv",
            "factor_holdout_rankings.csv",
            "latest_holdings.csv",
            "portfolio_returns.csv",
            "benchmark_returns.csv",
            "factor_scores.csv",
            "skipped_reasons.csv",
            "run_config.json",
            "run_metadata.json",
            "report.md",
            "report.html",
        ]
        for name in expected:
            self.assertTrue((out / name).exists(), name)
        rankings = _read_csv(out / "factor_rankings.csv")
        self.assertTrue(rankings)
        for col in RANKING_COLUMNS:
            self.assertIn(col, rankings[0])
        metrics = _read_csv(out / "factor_metrics.csv")
        for col in METRIC_COLUMNS:
            self.assertIn(col, metrics[0])
        holdings = _read_csv(out / "latest_holdings.csv")
        self.assertTrue(holdings)
        for col in HOLDING_COLUMNS:
            self.assertIn(col, holdings[0])
        self.assertAlmostEqual(sum(float(h["weight"]) for h in holdings), 1.0, places=6)

    def test_metadata_and_report_include_caveats_and_timing(self):
        out = self.run_cli()
        metadata = json.loads((out / "run_metadata.json").read_text())
        self.assertIn("ranking_formula", metadata)
        self.assertIn("holdout_validation", metadata)
        self.assertIn("best_factor_holdout_rank", metadata["holdout_validation"])
        self.assertIn("timing_convention", metadata)
        self.assertIn("same-close", metadata["timing_convention"])
        self.assertFalse(metadata["universe_is_point_in_time"])
        self.assertIn("market_cap_filter_basis", metadata)
        self.assertFalse(metadata["market_cap_filter_attempted"])
        self.assertFalse(metadata["market_cap_filter_effective"])
        self.assertEqual(metadata["filter_fallback_reason"], "none")
        self.assertIn("universe_scope_note", metadata)
        self.assertIn("coverage_denominator", metadata)
        self.assertIn("rankable_stock_universe_count", metadata)
        self.assertIn("active_priced_stock_count", metadata)
        self.assertIn("latest_factor_eligible_ticker_count", metadata)
        self.assertIn("factor_eligibility_note", metadata)
        self.assertEqual(metadata["transaction_cost_model"], "one_way_notional")
        self.assertIn("one-way traded notional", metadata["transaction_cost_note"])
        self.assertIn("latest_portfolio_effective_holdings", metadata)
        self.assertIn("latest_portfolio_top5_weight", metadata)
        self.assertIn("latest_portfolio_capacity_10pct_adv", metadata)
        self.assertIn("latest_portfolio_capacity_note", metadata)
        self.assertIn("ADV", metadata["latest_portfolio_capacity_note"])
        self.assertIn("latest_portfolio_average_turnover", metadata)
        self.assertIn("market_cap_filter_status", metadata)
        self.assertIn("rebalance_frequency", metadata)
        self.assertIn("benchmark_tickers", metadata)
        self.assertIn("benchmark_note", metadata)
        self.assertIn("current_screen_note", metadata)
        self.assertTrue(metadata["caveats"])
        report = (out / "report.md").read_text()
        html_report = (out / "report.html").read_text()
        self.assertIn("Best factor", report)
        self.assertIn("Sharpe", report)
        self.assertIn("Sortino", report)
        self.assertIn("Calmar", report)
        self.assertIn("Max drawdown", report)
        self.assertIn("Best Factor Dashboard", html_report)
        self.assertIn("Factor Ranking", html_report)
        self.assertIn("Latest Holdings", html_report)
        self.assertIn("Free-Data Limitations", html_report)
        self.assertNotIn('src="http', html_report.lower())
        self.assertNotIn('href="http', html_report.lower())
        self.assertNotIn("@import", html_report.lower())
        self.assertNotIn(str(FIXTURES), report)
        self.assertNotIn(str(FIXTURES), html_report)
        for caveat in CAVEATS[:2]:
            self.assertIn(caveat, report)
            self.assertIn(caveat, html_report)

    def test_default_run_uses_zoo_preset_metadata(self):
        out = tempfile.TemporaryDirectory()
        self.addCleanup(out.cleanup)
        cmd = [
            sys.executable,
            "-m",
            "best_factor.cli",
            "run",
            "--prices-file",
            str(FIXTURES / "prices.csv"),
            "--universe-file",
            str(FIXTURES / "universe.csv"),
            "--fundamentals-file",
            str(FIXTURES / "fundamentals.csv"),
            "--output-dir",
            out.name,
            "--rebalance",
            "M",
            "--top-n",
            "3",
        ]
        completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        metadata = json.loads((Path(out.name) / "run_metadata.json").read_text())
        self.assertEqual(metadata["factor_preset"], "zoo")
        self.assertEqual(metadata["requested_factor_preset"], "zoo")
        self.assertGreaterEqual(metadata["factor_library_size"], 300)
        self.assertGreaterEqual(metadata["selected_factor_count"], 300)
        self.assertGreaterEqual(metadata["tested_factor_count"], 300)
        self.assertIn("factor_category_counts", metadata)
        self.assertIn("factor_kind_counts", metadata)
        self.assertIn("factor_family_summary", metadata)
        self.assertIn("factor_catalog", metadata)
        self.assertIn("skip_resolution_note", metadata)
        categories = {row["category"] for row in metadata["factor_family_summary"]}
        for category in ["distribution", "tail", "accumulation", "intraday", "trend_quality"]:
            self.assertIn(category, categories)
        self.assertTrue(any(row["name"] == "price_volume_corr_63d" for row in metadata["factor_catalog"]))
        self.assertIn("multiple-testing", " ".join(metadata["caveats"]))

    def test_market_cap_filter_fallback_metadata_is_explicit(self):
        out = self.run_cli(
            "--market-cap-filter-attempted",
            "--filter-fallback-reason",
            "market_cap_metadata_insufficient_preflight",
        )
        metadata = json.loads((out / "run_metadata.json").read_text())
        self.assertTrue(metadata["market_cap_filter_attempted"])
        self.assertFalse(metadata["market_cap_filter_effective"])
        self.assertEqual(metadata["market_cap_filter_basis"], "not_applied")
        self.assertEqual(metadata["filter_fallback_reason"], "market_cap_metadata_insufficient_preflight")
        self.assertIn("not_applied_metadata_insufficient", metadata["market_cap_filter_status"])

    def test_min_factor_eligible_tickers_gate_fails_before_claiming_large_universe(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            cache_dir = Path(tmp) / "cache"
            args = cli_module.build_parser().parse_args([
                "run",
                "--provider",
                "yfinance",
                "--tickers",
                "AAA",
                "BBB",
                "CCC",
                "--period",
                "5y",
                "--cache-dir",
                str(cache_dir),
                "--universe-file",
                str(FIXTURES / "universe.csv"),
                "--fundamentals-file",
                str(FIXTURES / "fundamentals.csv"),
                "--output-dir",
                str(output_dir),
                "--rebalance",
                "M",
                "--top-n",
                "3",
                "--factor-preset",
                "core",
                "--min-factor-eligible-tickers",
                "9",
            ])

            def fake_fetch(tickers, period, cache_dir_arg, **kwargs):
                return load_prices_csv(FIXTURES / "prices.csv"), {
                    "provider": "yfinance",
                    "provider_version": "test",
                    "fetched_at": "2026-06-11T00:00:00Z",
                    "source": "yfinance:test",
                    "cache_dir": str(cache_dir_arg),
                    "requested_ticker_count": len(tickers),
                    "succeeded_tickers": list(tickers),
                    "failed_tickers": [],
                }

            with mock.patch("best_factor.cli.fetch_yfinance_prices", side_effect=fake_fetch):
                with self.assertRaisesRegex(ValueError, "below --min-factor-eligible-tickers"):
                    cli_module.run(args)

    def test_yfinance_rejects_benchmark_overlap_before_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = cli_module.build_parser().parse_args([
                "run",
                "--provider",
                "yfinance",
                "--tickers",
                "AAA",
                "QQQ",
                "--benchmark-tickers",
                "QQQ",
                "--output-dir",
                str(Path(tmp) / "out"),
            ])
            with self.assertRaisesRegex(ValueError, r"benchmark ticker\(s\) must not also"):
                cli_module.run(args)

    def test_yfinance_stock_tickers_are_deduped_before_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            cache_dir = Path(tmp) / "cache"
            calls = []

            def fake_fetch(tickers, period, cache_dir_arg, **kwargs):
                calls.append(list(tickers))
                return load_prices_csv(FIXTURES / "prices.csv"), {
                    "provider": "yfinance",
                    "provider_version": "test",
                    "fetched_at": "2026-06-11T00:00:00Z",
                    "source": "yfinance:test",
                    "cache_dir": str(cache_dir_arg),
                    "requested_ticker_count": len(tickers),
                    "succeeded_tickers": list(tickers),
                    "failed_tickers": [],
                }

            args = cli_module.build_parser().parse_args([
                "run",
                "--provider",
                "yfinance",
                "--tickers",
                "AAA",
                "AAA",
                "BBB",
                "aaa",
                "CCC",
                "--period",
                "5y",
                "--cache-dir",
                str(cache_dir),
                "--universe-file",
                str(FIXTURES / "universe.csv"),
                "--fundamentals-file",
                str(FIXTURES / "fundamentals.csv"),
                "--output-dir",
                str(output_dir),
                "--rebalance",
                "M",
                "--top-n",
                "3",
                "--factor-preset",
                "core",
            ])

            with mock.patch("best_factor.cli.fetch_yfinance_prices", side_effect=fake_fetch):
                cli_module.run(args)

        self.assertEqual(calls, [["AAA", "BBB", "CCC"]])

    def test_resilient_provider_records_fallback_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            cache_dir = Path(tmp) / "cache"
            calls = []

            def fake_fetch(tickers, period, cache_dir_arg, **kwargs):
                calls.append(list(tickers))
                return load_prices_csv(FIXTURES / "prices.csv"), {
                    "provider": "yfinance_yahoo_chart",
                    "provider_version": "yfinance:test; yahoo_chart:direct-json-v8",
                    "fetched_at": "2026-06-11T00:00:00Z",
                    "source": "test resilient provider",
                    "cache_dir": str(cache_dir_arg),
                    "requested_ticker_count": len(tickers),
                    "succeeded_tickers": list(tickers),
                    "failed_tickers": [],
                    "provider_order": ["yfinance", "yahoo_chart"],
                    "provider_attempted_sources": ["yfinance", "yahoo_chart"],
                    "provider_fill_counts": {"yfinance": max(0, len(tickers) - 1), "yahoo_chart": 1},
                    "provider_failed_tickers_by_source": {"yfinance": ["CCC"], "yahoo_chart": []},
                    "provider_error_count": 1,
                    "fallback_source": "yahoo_chart",
                    "fallback_filled_ticker_count": 1,
                    "fallback_filled_tickers": ["CCC"],
                }

            args = cli_module.build_parser().parse_args([
                "run",
                "--provider",
                "yfinance_yahoo_chart",
                "--tickers",
                "AAA",
                "BBB",
                "CCC",
                "--period",
                "5y",
                "--cache-dir",
                str(cache_dir),
                "--universe-file",
                str(FIXTURES / "universe.csv"),
                "--fundamentals-file",
                str(FIXTURES / "fundamentals.csv"),
                "--output-dir",
                str(output_dir),
                "--rebalance",
                "M",
                "--top-n",
                "3",
                "--factor-preset",
                "core",
            ])

            with mock.patch("best_factor.cli.fetch_resilient_prices", side_effect=fake_fetch):
                cli_module.run(args)
            metadata = json.loads((output_dir / "run_metadata.json").read_text())

        self.assertEqual(calls, [["AAA", "BBB", "CCC"]])
        self.assertEqual(metadata["provider"], "yfinance_yahoo_chart")
        self.assertEqual(metadata["provider_order"], ["yfinance", "yahoo_chart"])
        self.assertEqual(metadata["provider_attempted_sources"], ["yfinance", "yahoo_chart"])
        self.assertEqual(metadata["provider_fill_counts"]["yahoo_chart"], 1)
        self.assertEqual(metadata["fallback_filled_ticker_count"], 1)

    def test_latest_price_coverage_uses_latest_broad_reference_date(self):
        prices = [
            {"ticker": "AAA", "date": dt.date(2026, 6, 12), "adj_close": 10.0, "volume": 100},
            {"ticker": "BBB", "date": dt.date(2026, 6, 12), "adj_close": 10.0, "volume": 100},
            {"ticker": "CCC", "date": dt.date(2026, 6, 12), "adj_close": 10.0, "volume": 100},
            {"ticker": "AAA", "date": dt.date(2026, 6, 15), "adj_close": 11.0, "volume": 100},
        ]
        coverage = cli_module._latest_price_coverage(prices, min_coverage_ratio=0.9)
        self.assertEqual(coverage["latest_data_reference_date"], "2026-06-12")
        self.assertEqual(coverage["latest_data_max_date"], "2026-06-15")
        self.assertEqual(coverage["latest_data_ticker_count"], 3)
        self.assertEqual(coverage["latest_data_max_date_ticker_count"], 1)
        self.assertAlmostEqual(coverage["latest_data_coverage_ratio"], 1.0)
        self.assertIn("ignored", coverage["latest_data_reference_note"])

    def test_site_subcommand_exports_github_pages_json(self):
        out = self.run_cli()
        site_json = out / "site" / "latest-results.json"
        cmd = [
            sys.executable,
            "-m",
            "best_factor.cli",
            "site",
            "--run-dir",
            str(out),
            "--output-file",
            str(site_json),
            "--data-scope",
            "fixture_sample",
        ]
        completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(site_json.read_text())
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["data_scope"], "fixture_sample")
        self.assertTrue(payload["rankings"])
        self.assertTrue(payload["latest_holdings"])
        self.assertIn("static_data_warning", payload["summary"])
        self.assertIn("factor_period_returns", payload)
        self.assertIn("benchmark_returns", payload)

    def test_benchmark_ticker_writes_nasdaq_comparison_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            prices = _read_csv(FIXTURES / "prices.csv")
            benchmark_rows = []
            for row in prices:
                if row["ticker"] != "AAA":
                    continue
                cloned = dict(row)
                cloned["ticker"] = "^IXIC"
                cloned["source"] = "fixture_benchmark"
                benchmark_rows.append(cloned)
            benchmark_prices = tmp_path / "prices_with_benchmark.csv"
            _write_csv(benchmark_prices, [*prices, *benchmark_rows])
            out = tmp_path / "out"
            cmd = [
                sys.executable,
                "-m",
                "best_factor.cli",
                "run",
                "--prices-file",
                str(benchmark_prices),
                "--universe-file",
                str(FIXTURES / "universe.csv"),
                "--fundamentals-file",
                str(FIXTURES / "fundamentals.csv"),
                "--output-dir",
                str(out),
                "--rebalance",
                "M",
                "--top-n",
                "3",
                "--factor-preset",
                "core",
                "--benchmark-tickers",
                "^IXIC",
            ]
            completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            benchmark_returns = _read_csv(out / "benchmark_returns.csv")
            metadata = json.loads((out / "run_metadata.json").read_text())
        self.assertTrue(benchmark_returns)
        self.assertEqual(benchmark_returns[0]["benchmark"], "Nasdaq Composite")
        self.assertEqual(benchmark_returns[0]["ticker"], "^IXIC")
        self.assertEqual(metadata["benchmark_tickers"], ["^IXIC"])
        self.assertEqual(metadata["price_ticker_count"], 8)
        self.assertEqual(metadata["benchmark_return_count"], len(benchmark_returns))
        self.assertIn("never included in stock selection", metadata["benchmark_note"])

    def test_yfinance_benchmark_failure_records_error_without_aborting_stock_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_dir = tmp_path / "out"
            cache_dir = tmp_path / "cache"
            stock_prices = load_prices_csv(FIXTURES / "prices.csv")
            calls = []

            def fake_fetch(tickers, period, cache_dir_arg, **kwargs):
                calls.append(list(tickers))
                if list(tickers) == ["^IXIC"]:
                    raise RuntimeError("benchmark provider unavailable")
                return stock_prices, {
                    "provider": "yfinance",
                    "provider_version": "test",
                    "fetched_at": "2026-06-11T00:00:00Z",
                    "source": "yfinance:test",
                    "cache_dir": str(cache_dir_arg),
                    "succeeded_tickers": list(tickers),
                    "failed_tickers": [],
                }

            args = cli_module.build_parser().parse_args([
                "run",
                "--provider",
                "yfinance",
                "--tickers",
                "AAA",
                "BBB",
                "CCC",
                "--period",
                "5y",
                "--cache-dir",
                str(cache_dir),
                "--universe-file",
                str(FIXTURES / "universe.csv"),
                "--fundamentals-file",
                str(FIXTURES / "fundamentals.csv"),
                "--output-dir",
                str(output_dir),
                "--rebalance",
                "M",
                "--top-n",
                "3",
                "--factor-preset",
                "core",
                "--benchmark-tickers",
                "^IXIC",
            ])

            with mock.patch("best_factor.cli.fetch_yfinance_prices", side_effect=fake_fetch):
                result = cli_module.run(args)

            metadata = json.loads((output_dir / "run_metadata.json").read_text())
            benchmark_returns = _read_csv(output_dir / "benchmark_returns.csv")

        self.assertEqual(result["output_dir"], str(output_dir))
        self.assertEqual(calls, [["AAA", "BBB", "CCC"], ["^IXIC"]])
        self.assertEqual(benchmark_returns, [])
        self.assertEqual(metadata["benchmark_tickers"], ["^IXIC"])
        self.assertEqual(metadata["benchmark_return_count"], 0)
        self.assertEqual(metadata["benchmark_succeeded_tickers"], [])
        self.assertEqual(metadata["benchmark_failed_tickers"], ["^IXIC"])
        self.assertIn("RuntimeError: benchmark provider unavailable", metadata["benchmark_error"])

    def test_yfinance_benchmark_proxy_records_actual_available_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output_dir = tmp_path / "out"
            cache_dir = tmp_path / "cache"
            stock_prices = load_prices_csv(FIXTURES / "prices.csv")
            benchmark_prices = []
            for row in stock_prices:
                if row["ticker"] != "AAA":
                    continue
                cloned = dict(row)
                cloned["ticker"] = "ONEQ"
                cloned["source"] = "fixture_benchmark_proxy"
                benchmark_prices.append(cloned)

            def fake_fetch(tickers, period, cache_dir_arg, **kwargs):
                if list(tickers) == ["^IXIC", "ONEQ"]:
                    return benchmark_prices, {
                        "provider": "yfinance",
                        "provider_version": "test",
                        "fetched_at": "2026-06-11T00:00:00Z",
                        "source": "yfinance:test",
                        "cache_dir": str(cache_dir_arg),
                        "succeeded_tickers": ["ONEQ"],
                        "failed_tickers": ["^IXIC"],
                    }
                return stock_prices, {
                    "provider": "yfinance",
                    "provider_version": "test",
                    "fetched_at": "2026-06-11T00:00:00Z",
                    "source": "yfinance:test",
                    "cache_dir": str(cache_dir_arg),
                    "succeeded_tickers": list(tickers),
                    "failed_tickers": [],
                }

            args = cli_module.build_parser().parse_args([
                "run",
                "--provider",
                "yfinance",
                "--tickers",
                "AAA",
                "BBB",
                "CCC",
                "--period",
                "5y",
                "--cache-dir",
                str(cache_dir),
                "--universe-file",
                str(FIXTURES / "universe.csv"),
                "--fundamentals-file",
                str(FIXTURES / "fundamentals.csv"),
                "--output-dir",
                str(output_dir),
                "--rebalance",
                "M",
                "--top-n",
                "3",
                "--factor-preset",
                "core",
                "--benchmark-tickers",
                "^IXIC",
                "ONEQ",
            ])

            with mock.patch("best_factor.cli.fetch_yfinance_prices", side_effect=fake_fetch):
                cli_module.run(args)

            metadata = json.loads((output_dir / "run_metadata.json").read_text())
            benchmark_returns = _read_csv(output_dir / "benchmark_returns.csv")

        self.assertTrue(benchmark_returns)
        self.assertEqual(benchmark_returns[0]["benchmark"], "Nasdaq Composite ETF proxy")
        self.assertEqual(benchmark_returns[0]["ticker"], "ONEQ")
        self.assertEqual(metadata["benchmark_tickers"], ["^IXIC", "ONEQ"])
        self.assertEqual(metadata["benchmark_succeeded_tickers"], ["ONEQ"])
        self.assertEqual(metadata["benchmark_failed_tickers"], ["^IXIC"])

    def test_min_price_tickers_gate_fails_before_claiming_large_universe(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            cache_dir = Path(tmp) / "cache"
            args = cli_module.build_parser().parse_args([
                "run",
                "--provider",
                "yfinance",
                "--tickers",
                "AAA",
                "BBB",
                "CCC",
                "--period",
                "5y",
                "--cache-dir",
                str(cache_dir),
                "--universe-file",
                str(FIXTURES / "universe.csv"),
                "--fundamentals-file",
                str(FIXTURES / "fundamentals.csv"),
                "--output-dir",
                str(output_dir),
                "--rebalance",
                "M",
                "--top-n",
                "3",
                "--factor-preset",
                "core",
                "--min-price-tickers",
                "9",
            ])

            def fake_fetch(tickers, period, cache_dir_arg, **kwargs):
                return load_prices_csv(FIXTURES / "prices.csv"), {
                    "provider": "yfinance",
                    "provider_version": "test",
                    "fetched_at": "2026-06-11T00:00:00Z",
                    "source": "yfinance:test",
                    "cache_dir": str(cache_dir_arg),
                    "requested_ticker_count": len(tickers),
                    "succeeded_tickers": ["AAA", "BBB", "CCC"],
                    "failed_tickers": [],
                }

            with mock.patch("best_factor.cli.fetch_yfinance_prices", side_effect=fake_fetch):
                with self.assertRaisesRegex(ValueError, "below --min-price-tickers"):
                    cli_module.run(args)

    def test_price_coverage_gates_fail_before_claiming_large_universe(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "out"
            cache_dir = Path(tmp) / "cache"
            args = cli_module.build_parser().parse_args([
                "run",
                "--provider",
                "yfinance",
                "--tickers",
                "AAA",
                "BBB",
                "CCC",
                "DDD",
                "EEE",
                "FFF",
                "GGG",
                "HHH",
                "III",
                "JJJ",
                "--period",
                "5y",
                "--cache-dir",
                str(cache_dir),
                "--universe-file",
                str(FIXTURES / "universe.csv"),
                "--fundamentals-file",
                str(FIXTURES / "fundamentals.csv"),
                "--output-dir",
                str(output_dir),
                "--rebalance",
                "M",
                "--top-n",
                "3",
                "--factor-preset",
                "core",
                "--min-price-coverage-ratio",
                "0.90",
            ])

            def fake_fetch(tickers, period, cache_dir_arg, **kwargs):
                return load_prices_csv(FIXTURES / "prices.csv"), {
                    "provider": "yfinance",
                    "provider_version": "test",
                    "fetched_at": "2026-06-11T00:00:00Z",
                    "source": "yfinance:test",
                    "cache_dir": str(cache_dir_arg),
                    "requested_ticker_count": len(tickers),
                    "succeeded_tickers": ["AAA", "BBB", "CCC"],
                    "failed_tickers": ["III", "JJJ"],
                }

            with mock.patch("best_factor.cli.fetch_yfinance_prices", side_effect=fake_fetch):
                with self.assertRaisesRegex(ValueError, "below --min-price-coverage-ratio"):
                    cli_module.run(args)

    def test_skip_factor_scores_csv_uses_streaming_backtest_and_records_metadata(self):
        out = self.run_cli("--skip-factor-scores-csv")
        self.assertFalse((out / "factor_scores.csv").exists())
        metadata = json.loads((out / "run_metadata.json").read_text())
        rankings = _read_csv(out / "factor_rankings.csv")
        self.assertEqual(metadata["factor_scores_archive"], "skipped_for_large_live_run")
        self.assertEqual(metadata["min_price_coverage_ratio"], 0.0)
        self.assertEqual(metadata["min_latest_data_coverage_ratio"], 0.0)
        self.assertTrue(rankings)

    def test_skipped_reasons_are_stable(self):
        out = self.run_cli("--top-n", "99")
        reasons = _read_csv(out / "skipped_reasons.csv")
        reason_names = {r["skip_reason"] for r in reasons}
        self.assertIn("not_enough_assets", reason_names)
        self.assertIn("insufficient_history", reason_names)

    def test_invalid_cli_argument_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as out:
            cmd = [
                sys.executable,
                "-m",
                "best_factor.cli",
                "run",
                "--prices-file",
                str(FIXTURES / "prices.csv"),
                "--output-dir",
                out,
                "--rebalance",
                "Q",
            ]
            completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("invalid choice", completed.stderr)

    def test_missing_file_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as out:
            cmd = [
                sys.executable,
                "-m",
                "best_factor.cli",
                "run",
                "--prices-file",
                str(FIXTURES / "missing.csv"),
                "--output-dir",
                out,
            ]
            completed = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("prices file not found", completed.stderr)


def _read_csv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
