import csv
import datetime as dt
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from best_factor.data import load_fundamentals_csv
from best_factor.factors import compute_factor_scores
from best_factor.portfolio import run_backtests

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


class Revision2ContractsTest(unittest.TestCase):
    def test_point_in_time_fundamentals_before_and_after_available_at(self):
        prices = _simple_prices([dt.date(2024, 1, 31), dt.date(2024, 2, 29)], [100, 110])
        fundamentals = {"AAA": [{"as_of_date": dt.date(2023, 12, 31), "available_at": dt.date(2024, 2, 15), "pe_ratio": 10.0, "return_on_equity": 0.2}]}
        scores = compute_factor_scores(prices, [dt.date(2024, 1, 31), dt.date(2024, 2, 29)], fundamentals, ["value_pe"])
        jan = [s for s in scores if s["signal_date"] == dt.date(2024, 1, 31)][0]
        feb = [s for s in scores if s["signal_date"] == dt.date(2024, 2, 29)][0]
        self.assertFalse(jan["eligible"])
        self.assertEqual(jan["skip_reason"], "missing_fundamentals")
        self.assertTrue(feb["eligible"])

    def test_static_fundamentals_lacking_available_at_are_not_pit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fund.csv"
            path.write_text("ticker,pe_ratio,return_on_equity\nAAA,10,0.2\n")
            fundamentals = load_fundamentals_csv(path)
        prices = _simple_prices([dt.date(2024, 1, 31), dt.date(2024, 2, 29)], [100, 110])
        scores = compute_factor_scores(prices, [dt.date(2024, 2, 29)], fundamentals, ["quality_roe"])
        self.assertFalse(scores[0]["eligible"])
        self.assertEqual(scores[0]["skip_reason"], "missing_fundamentals")

    def test_missing_entry_or_exit_prices_skip_periods(self):
        prices = [
            {"ticker": "AAA", "date": dt.date(2024, 1, 31), "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "AAA", "date": dt.date(2024, 2, 29), "adj_close": 110.0, "volume": 1_000_000},
            {"ticker": "AAA", "date": dt.date(2024, 3, 29), "adj_close": 121.0, "volume": 1_000_000},
            {"ticker": "BBB", "date": dt.date(2024, 1, 31), "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "BBB", "date": dt.date(2024, 3, 29), "adj_close": 95.0, "volume": 1_000_000},
        ]
        universe = [{"ticker": "AAA", "market_cap": 1e9, "active": True, "asset_type": "stock"}, {"ticker": "BBB", "market_cap": 1e9, "active": True, "asset_type": "stock"}]
        scores = [
            {"factor": "test", "ticker": "AAA", "signal_date": dt.date(2024, 1, 31), "score": 1.0, "eligible": True, "skip_reason": ""},
            {"factor": "test", "ticker": "BBB", "signal_date": dt.date(2024, 1, 31), "score": 2.0, "eligible": True, "skip_reason": ""},
            {"factor": "test", "ticker": "AAA", "signal_date": dt.date(2024, 2, 29), "score": 1.0, "eligible": True, "skip_reason": ""},
            {"factor": "test", "ticker": "BBB", "signal_date": dt.date(2024, 2, 29), "score": 2.0, "eligible": True, "skip_reason": ""},
        ]
        result = run_backtests(
            prices,
            universe,
            scores,
            [dt.date(2024, 1, 31), dt.date(2024, 2, 29), dt.date(2024, 3, 29)],
            top_n=2,
            transaction_cost_bps=100,
        )
        self.assertIn("missing_exit_price", result["skipped_reasons"])
        self.assertIn("missing_rebalance_price", result["skipped_reasons"])
        self.assertIn("invalid_period_missing_price", result["skipped_reasons"])
        self.assertEqual(len(result["holdings"]), 0)
        self.assertEqual([row["holdings_count"] for row in result["returns"]], [0, 0])
        self.assertEqual([row["skip_reason"] for row in result["returns"]], ["invalid_period_missing_price", "invalid_period_missing_price"])
        self.assertAlmostEqual(result["returns"][0]["return"], 0.0)
        self.assertAlmostEqual(result["returns"][1]["return"], 0.0)

    def test_inactive_non_stock_and_not_enough_assets(self):
        prices = _simple_prices([dt.date(2024, 1, 31), dt.date(2024, 2, 29)], [100, 110])
        prices += [{"ticker": "BBB", "date": dt.date(2024, 1, 31), "adj_close": 100.0, "volume": 1_000_000}, {"ticker": "BBB", "date": dt.date(2024, 2, 29), "adj_close": 105.0, "volume": 1_000_000}]
        universe = [{"ticker": "AAA", "market_cap": 1e9, "active": True, "asset_type": "stock"}, {"ticker": "BBB", "market_cap": 1e9, "active": "false", "asset_type": "stock"}]
        scores = [
            {"factor": "test", "ticker": "AAA", "signal_date": dt.date(2024, 1, 31), "score": 1.0, "eligible": True, "skip_reason": ""},
            {"factor": "test", "ticker": "BBB", "signal_date": dt.date(2024, 1, 31), "score": 2.0, "eligible": True, "skip_reason": ""},
        ]
        result = run_backtests(prices, universe, scores, [dt.date(2024, 1, 31), dt.date(2024, 2, 29)], top_n=2)
        self.assertIn("inactive_or_non_stock", result["skipped_reasons"])
        self.assertIn("not_enough_assets", result["skipped_reasons"])

    def test_unknown_factor_cli_error(self):
        with tempfile.TemporaryDirectory() as out:
            completed = _run_cli(out, "--factors", "unknown_factor")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unknown_factor", completed.stderr)

    def test_empty_factors_flag_fails_argparse(self):
        with tempfile.TemporaryDirectory() as out:
            completed = _run_cli(out, "--factors")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("expected at least one argument", completed.stderr)

    def test_composite_only_emits_only_composite_ranking(self):
        with tempfile.TemporaryDirectory() as out:
            completed = _run_cli(out, "--factors", "composite_defensive")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with (Path(out) / "factor_rankings.csv").open(newline="") as f:
                rankings = list(csv.DictReader(f))
            factors = {row["factor"] for row in rankings}
        self.assertEqual(factors, {"composite_defensive"})

    def test_composite_requires_all_dependency_scores(self):
        short_dates = [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(70)]
        short_prices = _simple_prices(short_dates, [100 + i for i in range(70)])
        short_scores = compute_factor_scores(short_prices, [short_dates[-1]], {}, ["composite_defensive"], ["composite_defensive"])
        self.assertFalse(short_scores[0]["eligible"])
        self.assertEqual(short_scores[0]["skip_reason"], "insufficient_history")

        long_dates = [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(150)]
        long_prices = _simple_prices(long_dates, [100 + i for i in range(150)])
        long_scores = compute_factor_scores(long_prices, [long_dates[-1]], {}, ["composite_defensive"], ["composite_defensive"])
        self.assertTrue(long_scores[0]["eligible"])

    def test_all_empty_run_fails_controlled(self):
        with tempfile.TemporaryDirectory() as out:
            completed = _run_cli(out, "--min-dollar-volume", "1000000000000")
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("no factor produced holdings", completed.stderr)


def _simple_prices(dates, closes):
    return [
        {"ticker": "AAA", "date": date, "adj_close": close, "volume": 1_000_000}
        for date, close in zip(dates, closes)
    ]


def _run_cli(output_dir, *extra):
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
        str(output_dir),
        "--rebalance",
        "M",
        "--top-n",
        "3",
        "--factor-preset",
        "core",
        *extra,
    ]
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
