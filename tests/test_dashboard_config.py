import csv
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / ".github" / "scripts" / "dashboard_config.py"
PERSISTED_PATH = ROOT / ".github" / "best-factor-dashboard-config.json"
PUBLIC_PATH = ROOT / "docs" / "data" / "dashboard-config.json"
FIXTURES = ROOT / "tests" / "fixtures"

SPEC = importlib.util.spec_from_file_location("dashboard_config", SCRIPT_PATH)
assert SPEC and SPEC.loader
dashboard_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dashboard_config)


class DashboardConfigTest(unittest.TestCase):
    def test_private_config_is_strict_and_public_binding_matches_current_result(self):
        private_payload = json.loads(PERSISTED_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(private_payload), {"schema_version", "config", "config_hash"})
        config = dashboard_config.validate_envelope(private_payload)
        self.assertEqual(tuple(config), dashboard_config.CONFIG_KEYS)
        self.assertEqual(config, private_payload["config"])
        self.assertEqual(private_payload["config_hash"], dashboard_config.config_hash(config))

        public_payload = json.loads(PUBLIC_PATH.read_text(encoding="utf-8"))
        public_config, binding = dashboard_config.validate_public_envelope(public_payload)
        latest_payload = json.loads((ROOT / "docs" / "data" / "latest-results.json").read_text(encoding="utf-8"))
        self.assertEqual(set(public_payload), {"schema_version", "config", "config_hash", "result_binding"})
        self.assertEqual(
            set(public_payload["result_binding"]),
            {"generated_at", "source_hash", "data_end_date"},
        )
        self.assertEqual(public_config, config)
        self.assertEqual(binding, dashboard_config.build_result_binding(latest_payload))

    def test_manual_overlay_keeps_blanks_preserves_zero_and_deduplicates_factors(self):
        persisted = {
            **dashboard_config.DEFAULT_CONFIG,
            "factor_allowlist": ["momentum_6m"],
            "transaction_cost_bps": 5.0,
        }
        resolved = dashboard_config.resolve_config(
            persisted,
            {
                "period": "keep",
                "top_n": "",
                "transaction_cost_bps": "0",
                "min_market_cap": "-0",
                "factor_allowlist": "momentum_6m, momentum_6m low_volatility",
            },
        )
        self.assertEqual(resolved["period"], "5y")
        self.assertEqual(resolved["top_n"], 20)
        self.assertEqual(resolved["transaction_cost_bps"], 0.0)
        self.assertEqual(str(resolved["min_market_cap"]), "0.0")
        self.assertEqual(resolved["factor_allowlist"], ["momentum_6m", "low_volatility"])

    def test_preset_sentinel_explicitly_clears_saved_allowlist(self):
        persisted = {**dashboard_config.DEFAULT_CONFIG, "factor_allowlist": ["momentum_6m"]}
        resolved = dashboard_config.resolve_config(
            persisted,
            {"factor_preset": "core", "factor_allowlist": "__preset__"},
        )
        self.assertEqual(resolved["factor_preset"], "core")
        self.assertEqual(resolved["factor_allowlist"], [])

    def test_strict_validation_rejects_invalid_and_out_of_range_inputs(self):
        invalid = {
            "period": "3y",
            "top_n": "1.5",
            "min_market_cap": "-1",
            "min_dollar_volume": "inf",
            "eligibility_adv_window": "253",
            "transaction_cost_bps": "nan",
            "transaction_cost_model": "free",
            "factor_allowlist": "not_a_real_factor",
        }
        for key, value in invalid.items():
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    dashboard_config.resolve_config(
                        dashboard_config.DEFAULT_CONFIG,
                        {key: value},
                    )

    def test_envelope_rejects_unknown_fields_and_hash_drift(self):
        with self.assertRaises(ValueError):
            dashboard_config.normalize_config(
                {**dashboard_config.DEFAULT_CONFIG, "unknown": "unsafe"}
            )
        payload = dashboard_config.make_envelope(dashboard_config.DEFAULT_CONFIG)
        payload["config"]["top_n"] = 21
        with self.assertRaisesRegex(ValueError, "config_hash"):
            dashboard_config.validate_envelope(payload)

    def test_every_public_analysis_input_changes_the_python_config_binding(self):
        variants = {
            "period": "2y",
            "rebalance": "W",
            "top_n": 21,
            "weighting": "equal",
            "factor_preset": "core",
            "factor_allowlist": ["momentum_6m"],
            "min_market_cap": 0,
            "min_dollar_volume": 0,
            "eligibility_adv_window": 21,
            "transaction_cost_bps": 10,
            "transaction_cost_model": "portfolio_turnover",
        }
        baseline = dashboard_config.make_envelope(dashboard_config.DEFAULT_CONFIG)
        self.assertEqual(tuple(variants), dashboard_config.CONFIG_KEYS)
        for key, value in variants.items():
            with self.subTest(key=key):
                changed = dashboard_config.resolve_config(
                    dashboard_config.DEFAULT_CONFIG,
                    {key: value},
                )
                envelope = dashboard_config.make_envelope(changed)
                self.assertEqual(envelope["config"][key], value)
                self.assertNotEqual(envelope["config_hash"], baseline["config_hash"])

    def test_result_binding_rejects_missing_or_malformed_result_fields(self):
        valid = {
            "schema_version": 1,
            "generated_at": "2026-07-23T23:16:07Z",
            "summary": {
                "source_hash": "a54e4adee3d58bc3",
                "data_end_date": "2026-07-23",
            },
        }
        invalid_payloads = [
            {**valid, "schema_version": 2},
            {key: value for key, value in valid.items() if key != "generated_at"},
            {**valid, "generated_at": "2026-07-23"},
            {**valid, "summary": {"data_end_date": "2026-07-23"}},
            {**valid, "summary": {"source_hash": "not-a-hash", "data_end_date": "2026-07-23"}},
            {**valid, "summary": {"source_hash": "a54e4adee3d58bc3", "data_end_date": "23-07-2026"}},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    dashboard_config.build_result_binding(payload)

        public_payload = dashboard_config.make_public_envelope(
            dashboard_config.DEFAULT_CONFIG,
            valid,
        )
        public_payload["result_binding"]["extra"] = "not-allowed"
        with self.assertRaises(ValueError):
            dashboard_config.validate_public_envelope(public_payload)

    def test_schedule_resolution_is_byte_identical_to_persisted_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            envelope_output = Path(tmp) / "dashboard-config.json"
            values_output = Path(tmp) / "dashboard-config.values"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--persisted",
                    str(PERSISTED_PATH),
                    "--event-name",
                    "schedule",
                    "--envelope-output",
                    str(envelope_output),
                    "--values-output",
                    str(values_output),
                ],
                cwd=ROOT,
                env={
                    **os.environ,
                    "PYTHONPATH": str(ROOT / "src"),
                    "INPUT_TOP_N": "-999",
                    "INPUT_FACTOR_ALLOWLIST": "not_a_real_factor",
                },
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(envelope_output.read_bytes(), PERSISTED_PATH.read_bytes())
            self.assertEqual(len(values_output.read_bytes().split(b"\0")) - 1, 11)

    def test_publish_mode_binds_result_without_modifying_private_config(self):
        private_before = PERSISTED_PATH.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            public_output = Path(tmp) / "dashboard-config.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--mode",
                    "publish",
                    "--persisted",
                    str(PERSISTED_PATH),
                    "--result-file",
                    str(ROOT / "docs" / "data" / "latest-results.json"),
                    "--public-output",
                    str(public_output),
                ],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                text=True,
                capture_output=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(public_output.read_text(encoding="utf-8"))
            config, binding = dashboard_config.validate_public_envelope(payload)
            self.assertEqual(config, dashboard_config.load_config(PERSISTED_PATH))
            self.assertEqual(
                binding,
                dashboard_config.build_result_binding(
                    json.loads((ROOT / "docs" / "data" / "latest-results.json").read_text(encoding="utf-8"))
                ),
            )
            self.assertEqual(public_output.read_bytes(), PUBLIC_PATH.read_bytes())
        self.assertEqual(PERSISTED_PATH.read_bytes(), private_before)

    def test_workflow_exposes_maps_persists_and_archives_all_inputs(self):
        workflow = (ROOT / ".github" / "workflows" / "update-dashboard.yml").read_text(encoding="utf-8")
        dispatch_block = workflow.split("    inputs:\n", 1)[1].split("  schedule:\n", 1)[0]
        dispatch_ids = re.findall(r"^      ([a-z][a-z0-9_]*):$", dispatch_block, flags=re.MULTILINE)
        operational_inputs = {
            "allow_fallback",
            "control_run_id",
            "control_input_schema_version",
            "control_input_schema_hash",
            "control_config_hash_algorithm",
            "control_config_hash",
        }
        self.assertEqual(
            tuple(key for key in dispatch_ids if key not in operational_inputs),
            dashboard_config.CONFIG_KEYS,
        )
        for name in operational_inputs:
            self.assertEqual(dispatch_ids.count(name), 1)
        for index, key in enumerate(dashboard_config.CONFIG_KEYS):
            self.assertIn(f"INPUT_{key.upper()}", workflow)
            self.assertIn(f'{key.upper()}="${{CONFIG_VALUES[{index}]}}"', workflow)
        for cli_mapping in (
            '--period "${PERIOD}"',
            '--rebalance "${REBALANCE}"',
            '--top-n "${TOP_N}"',
            '--weighting "${WEIGHTING}"',
            'FACTOR_ARGS=(--factor-preset "${FACTOR_PRESET}")',
            'IFS=\',\' read -r -a FACTOR_NAMES <<< "${FACTOR_ALLOWLIST}"',
            '--min-market-cap "${MIN_MARKET_CAP}"',
            '--min-dollar-volume "${MIN_DOLLAR_VOLUME}"',
            '--eligibility-adv-window "${ELIGIBILITY_ADV_WINDOW}"',
            '--transaction-cost-bps "${TRANSACTION_COST_BPS}"',
            '--transaction-cost-model "${TRANSACTION_COST_MODEL}"',
        ):
            self.assertIn(cli_mapping, workflow)
        self.assertIn("python .github/scripts/dashboard_config.py", workflow)
        self.assertIn("node --test tests/common_design_v1.test.mjs tests/control_api.test.mjs", workflow)
        self.assertIn("--mode publish", workflow)
        self.assertIn("--result-file docs/data/latest-results.json", workflow)
        self.assertIn("--public-output docs/data/dashboard-config.json", workflow)
        self.assertLess(
            workflow.index("python -m best_factor.cli site"),
            workflow.index("--mode publish"),
        )
        self.assertLess(
            workflow.index("--mode publish"),
            workflow.index("cp /tmp/best-factor-effective-config.json .github/best-factor-dashboard-config.json"),
        )
        self.assertIn('MIN_MARKET_CAP_NAMES=20', workflow)
        self.assertNotIn("--requested-min-market-cap", workflow)
        self.assertIn('cp /tmp/best-factor-effective-config.json .github/best-factor-dashboard-config.json', workflow)
        self.assertNotIn('cp /tmp/best-factor-effective-config.json docs/data/dashboard-config.json', workflow)
        self.assertIn(
            "git add docs/data/latest-results.json docs/data/summary.json docs/data/dashboard-config.json .github/best-factor-dashboard-config.json",
            workflow,
        )
        self.assertIn("docs/data/dashboard-config.json", workflow)
        self.assertIn(".github/best-factor-dashboard-config.json", workflow)

    def test_manual_fallback_is_explicit_and_fail_closed(self):
        workflow = (ROOT / ".github" / "workflows" / "update-dashboard.yml").read_text(encoding="utf-8")
        dispatch_block = workflow.split("    inputs:\n", 1)[1].split("  schedule:\n", 1)[0]
        fallback_block = dispatch_block.split("      allow_fallback:\n", 1)[1]
        self.assertIn("default: false", fallback_block)
        self.assertIn("type: boolean", fallback_block)
        self.assertIn(
            "ALLOW_FALLBACK: ${{ github.event_name == 'workflow_dispatch' && inputs.allow_fallback }}",
            workflow,
        )
        self.assertIn(
            'echo "fallback policy: event=${EVENT_NAME} allow_fallback=${ALLOW_FALLBACK}"',
            workflow,
        )
        self.assertIn('if [[ "${ALLOW_FALLBACK}" != "true" ]]; then', workflow)
        self.assertIn("fallback is disabled, so no result will be published", workflow)
        self.assertLess(
            workflow.index('if [[ "${ALLOW_FALLBACK}" != "true" ]]; then'),
            workflow.index("--filter-fallback-reason market_cap_metadata_insufficient_preflight"),
        )
        self.assertIn("control=${{ inputs.control_run_id || 'direct' }}", workflow)
        self.assertIn("CONTROL_RUN_ID: ${{ inputs.control_run_id }}", workflow)
        self.assertIn("control correlation: control_run_id=${CONTROL_RUN_ID:-direct} github_run_id=${GITHUB_RUN_ID}", workflow)
        self.assertIn('CONTROL_CONFIG_HASH_ALGORITHM}" != "best-factor-python-json-v1"', workflow)
        self.assertIn("Control API dispatch must provide every analytical input explicitly.", workflow)
        self.assertIn('CONTROL_ANALYSIS_FACTOR_ALLOWLIST: ${{ inputs.factor_allowlist }}', workflow)

    def test_control_callback_uses_exact_immutable_artifact_and_bounded_binding(self):
        workflow = (ROOT / ".github" / "workflows" / "update-dashboard.yml").read_text(encoding="utf-8")
        callback_script = (ROOT / ".github" / "scripts" / "control_callback.py").read_text(
            encoding="utf-8"
        )
        deploy_index = workflow.index("- name: Deploy to GitHub Pages")
        readback_index = workflow.index("- name: Verify immutable control-run artifact")
        callback_index = workflow.index("- name: Publish control-run result manifest")
        self.assertLess(deploy_index, readback_index)
        self.assertLess(readback_index, callback_index)
        self.assertIn("id: data_commit", workflow)
        self.assertIn(
            'PUBLIC_RESULT_URL="https://raw.githubusercontent.com/SonChangGi/best-factor/${DATA_COMMIT_SHA}/docs/data/latest-results.json"',
            workflow,
        )
        self.assertIn("cmp --silent docs/data/latest-results.json /tmp/best-factor-public-latest-results.json", workflow)
        self.assertIn("QUANT_CONTROL_CALLBACK_URL: ${{ secrets.QUANT_CONTROL_CALLBACK_URL }}", workflow)
        self.assertIn(
            "QUANT_CONTROL_WORKER_CALLBACK_TOKEN: ${{ secrets.QUANT_CONTROL_WORKER_CALLBACK_TOKEN }}",
            workflow,
        )
        self.assertIn(
            '--header "Authorization: Bearer ${QUANT_CONTROL_WORKER_CALLBACK_TOKEN}"',
            workflow,
        )
        self.assertIn(
            'CALLBACK_ENDPOINT="${QUANT_CONTROL_CALLBACK_URL%/}/v1/internal/runs/${CONTROL_RUN_ID}/result-manifest"',
            workflow,
        )
        self.assertIn("python .github/scripts/control_callback.py result", workflow)
        self.assertIn("python .github/scripts/control_callback.py failure", workflow)
        self.assertNotIn("python - <<'PY'", workflow[callback_index:])
        for field in (
            '"binding": binding',
            '"projectId": "best-factor"',
            '"requestedInputs": requested_inputs',
            '"normalizedInputs": requested_inputs',
            '"effectiveConfigHash": effective_config_hash',
            '"effectiveInputs": requested_inputs',
            '"ignoredInputs": []',
            '"fallbacks": []',
            '"fallbackUsed": False',
            '"fallbackReason": None',
            '"dataIdentity": {',
            '"artifact": {',
            '"sha256": hashlib.sha256(result_bytes).hexdigest()',
            '"byteSize": len(result_bytes)',
            '"contractVersion": "best-factor/latest-results/v1"',
            '"payload": bounded_payload',
        ):
            self.assertIn(field, callback_script)
        self.assertIn("SUMMARY_ALLOWLIST = (", callback_script)
        self.assertIn('"best_factor"', callback_script)
        self.assertIn("if len(bounded_bytes) > 64 * 1024:", callback_script)
        self.assertIn(
            "Control callback URL must be an HTTPS base without credentials, query, or fragment",
            callback_script,
        )
        self.assertIn("/v1/internal/runs/${CONTROL_RUN_ID}/failure", workflow)
        self.assertIn('"providerRunId": f"github-actions:{binding[\'runId\']}"', callback_script)
        self.assertIn('"errorCode": "worker_workflow_failed"', callback_script)
        self.assertIn('source_hash = summary.get("source_hash") or metadata.get("source_hash")', callback_script)
        self.assertIn('r"[0-9a-fA-F]{8,128}"', callback_script)
        self.assertNotIn("source_hash.ljust", callback_script)
        self.assertNotIn("source_hash.rjust", callback_script)
        compile(callback_script, "best-factor-control-callback", "exec")

    def test_existing_cli_same_inputs_are_deterministic_and_true_top_n_changes_results(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second, tempfile.TemporaryDirectory() as top_one:
            self._run_fixture(first, top_n=3)
            self._run_fixture(second, top_n=3)
            self._run_fixture(top_one, top_n=1)
            analysis_artifacts = (
                "factor_rankings.csv",
                "factor_metrics.csv",
                "factor_holdout_rankings.csv",
                "factor_holdout_metrics.csv",
                "factor_scores.csv",
                "latest_holdings.csv",
                "portfolio_returns.csv",
            )
            for name in analysis_artifacts:
                self.assertEqual((Path(first) / name).read_bytes(), (Path(second) / name).read_bytes(), name)
            first_rankings = self._read_csv(Path(first) / "factor_rankings.csv")
            first_holdings = self._read_csv(Path(first) / "latest_holdings.csv")
            top_one_holdings = self._read_csv(Path(top_one) / "latest_holdings.csv")
            self.assertEqual(first_rankings[0]["factor"], "quality_roe")
            self.assertEqual(len(first_rankings), 9)
            self.assertEqual(len(first_holdings), 3)
            self.assertEqual(len(top_one_holdings), 1)
            self.assertNotEqual(
                (Path(first) / "portfolio_returns.csv").read_bytes(),
                (Path(top_one) / "portfolio_returns.csv").read_bytes(),
            )

    def test_existing_cli_analysis_inputs_change_the_expected_artifacts(self):
        with (
            tempfile.TemporaryDirectory() as baseline,
            tempfile.TemporaryDirectory() as score_weighted,
            tempfile.TemporaryDirectory() as weekly,
            tempfile.TemporaryDirectory() as high_cost,
            tempfile.TemporaryDirectory() as turnover_cost,
            tempfile.TemporaryDirectory() as explicit_factors,
            tempfile.TemporaryDirectory() as zoo_preset,
            tempfile.TemporaryDirectory() as large_cap,
            tempfile.TemporaryDirectory() as short_adv,
            tempfile.TemporaryDirectory() as long_adv,
        ):
            self._run_fixture(baseline, top_n=3)
            self._run_fixture(score_weighted, top_n=3, weighting="score")
            self._run_fixture(weekly, top_n=3, rebalance="W")
            self._run_fixture(high_cost, top_n=3, transaction_cost_bps=100)
            self._run_fixture(
                turnover_cost,
                top_n=3,
                transaction_cost_bps=100,
                transaction_cost_model="portfolio_turnover",
            )
            self._run_fixture(
                explicit_factors,
                top_n=3,
                factors=("momentum_6m", "low_volatility"),
            )
            self._run_fixture(zoo_preset, top_n=3, factor_preset="zoo")
            self._run_fixture(large_cap, top_n=3, min_market_cap=100_000_000_000)
            self._run_fixture(
                short_adv,
                top_n=3,
                min_dollar_volume=100_000_000,
                eligibility_adv_window=21,
            )
            self._run_fixture(
                long_adv,
                top_n=3,
                min_dollar_volume=100_000_000,
                eligibility_adv_window=63,
            )

            baseline_returns = (Path(baseline) / "portfolio_returns.csv").read_bytes()
            self.assertNotEqual(
                baseline_returns,
                (Path(score_weighted) / "portfolio_returns.csv").read_bytes(),
            )
            self.assertNotEqual(
                baseline_returns,
                (Path(weekly) / "portfolio_returns.csv").read_bytes(),
            )
            self.assertNotEqual(
                baseline_returns,
                (Path(high_cost) / "portfolio_returns.csv").read_bytes(),
            )
            self.assertNotEqual(
                (Path(high_cost) / "portfolio_returns.csv").read_bytes(),
                (Path(turnover_cost) / "portfolio_returns.csv").read_bytes(),
            )
            self.assertNotEqual(
                baseline_returns,
                (Path(large_cap) / "portfolio_returns.csv").read_bytes(),
            )
            self.assertNotEqual(
                (Path(short_adv) / "portfolio_returns.csv").read_bytes(),
                (Path(long_adv) / "portfolio_returns.csv").read_bytes(),
            )
            explicit_rankings = self._read_csv(Path(explicit_factors) / "factor_rankings.csv")
            self.assertEqual(
                {row["factor"] for row in explicit_rankings},
                {"momentum_6m", "low_volatility"},
            )
            self.assertGreater(
                len(self._read_csv(Path(zoo_preset) / "factor_rankings.csv")),
                len(self._read_csv(Path(baseline) / "factor_rankings.csv")),
            )

    def _run_fixture(
        self,
        output_dir: str,
        *,
        top_n: int,
        rebalance: str = "M",
        weighting: str = "equal",
        transaction_cost_bps: float = 0,
        transaction_cost_model: str = "one_way_notional",
        factors: tuple[str, ...] | None = None,
        factor_preset: str = "core",
        min_market_cap: float = 0,
        min_dollar_volume: float = 0,
        eligibility_adv_window: int = 63,
    ) -> None:
        factor_args = ["--factors", *factors] if factors else ["--factor-preset", factor_preset]
        completed = subprocess.run(
            [
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
                output_dir,
                "--rebalance",
                rebalance,
                "--top-n",
                str(top_n),
                "--weighting",
                weighting,
                "--transaction-cost-bps",
                str(transaction_cost_bps),
                "--transaction-cost-model",
                transaction_cost_model,
                "--min-market-cap",
                str(min_market_cap),
                "--min-dollar-volume",
                str(min_dollar_volume),
                "--eligibility-adv-window",
                str(eligibility_adv_window),
                *factor_args,
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            text=True,
            capture_output=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))


if __name__ == "__main__":
    unittest.main()
