import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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
            "latest_holdings.csv",
            "portfolio_returns.csv",
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
        self.assertIn("timing_convention", metadata)
        self.assertIn("same-close", metadata["timing_convention"])
        self.assertFalse(metadata["universe_is_point_in_time"])
        self.assertIn("market_cap_filter_basis", metadata)
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
        self.assertGreaterEqual(metadata["factor_library_size"], 200)
        self.assertGreaterEqual(metadata["selected_factor_count"], 200)
        self.assertGreaterEqual(metadata["tested_factor_count"], 200)
        self.assertIn("factor_category_counts", metadata)
        self.assertIn("multiple-testing", " ".join(metadata["caveats"]))

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


if __name__ == "__main__":
    unittest.main()
