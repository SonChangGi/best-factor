import datetime as dt
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "control_callback.py"
SPEC = importlib.util.spec_from_file_location("control_callback", SCRIPT)
assert SPEC and SPEC.loader
control_callback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(control_callback)


def callback_environment() -> dict[str, str]:
    return {
        "QUANT_CONTROL_CALLBACK_URL": "https://control.example.test",
        "CONTROL_RUN_ID": "12345678-1234-4234-8234-123456789abc",
        "CONTROL_INPUT_SCHEMA_VERSION": "best-factor/input/v1",
        "CONTROL_INPUT_SCHEMA_HASH": "a" * 64,
        "CONTROL_CONFIG_HASH_ALGORITHM": "best-factor-python-json-v1",
        "CONTROL_CONFIG_HASH": "b" * 64,
        "ARTIFACT_URL": "https://raw.githubusercontent.com/example/result.json",
        "CODE_VERSION": "c" * 40,
    }


class ControlCallbackScriptTests(unittest.TestCase):
    def test_result_manifest_preserves_binding_and_bounds_the_result_payload(self):
        result = {
            "schema_version": 1,
            "generated_at": "2026-08-14T01:02:03Z",
            "data_scope": "live_resilient_current_common_stock_liquidity_screen_actions",
            "summary": {
                "best_factor": "momentum",
                "data_end_date": "2026-08-13",
                "source_hash": "0123456789abcdef",
                "not_callback_safe": "must not be forwarded",
            },
            "metadata": {},
        }
        config = {"config_hash": "b" * 64, "config": {"top_n": 20}}
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            result_path = temporary_path / "result.json"
            config_path = temporary_path / "config.json"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            config_path.write_text(json.dumps(config), encoding="utf-8")
            manifest = control_callback.build_result_manifest(
                result_path,
                config_path,
                environment=callback_environment(),
            )

        self.assertEqual(manifest["binding"]["projectId"], "best-factor")
        self.assertEqual(manifest["requestedInputs"], {"top_n": 20})
        self.assertEqual(manifest["effectiveConfigHash"], "b" * 64)
        self.assertEqual(manifest["dataAsOf"], "2026-08-13")
        self.assertEqual(manifest["payload"]["summary"], {
            "best_factor": "momentum",
            "data_end_date": "2026-08-13",
            "source_hash": "0123456789abcdef",
        })
        self.assertEqual(
            manifest["artifact"]["sha256"],
            hashlib.sha256(json.dumps(result).encode("utf-8")).hexdigest(),
        )
        self.assertEqual(manifest["artifact"]["contractVersion"], "best-factor/latest-results/v1")

    def test_result_manifest_fails_closed_on_config_binding_drift(self):
        result = {
            "schema_version": 1,
            "generated_at": "2026-08-14T01:02:03Z",
            "data_scope": "fixture",
            "summary": {
                "data_end_date": "2026-08-13",
                "source_hash": "0123456789abcdef",
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            result_path = temporary_path / "result.json"
            config_path = temporary_path / "config.json"
            result_path.write_text(json.dumps(result), encoding="utf-8")
            config_path.write_text(
                json.dumps({"config_hash": "d" * 64, "config": {"top_n": 20}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SystemExit, "config hash drifted"):
                control_callback.build_result_manifest(
                    result_path,
                    config_path,
                    environment=callback_environment(),
                )

    def test_failure_manifest_and_callback_url_validation_are_deterministic(self):
        occurred_at = dt.datetime(2026, 8, 14, 1, 2, 3, tzinfo=dt.UTC)
        manifest = control_callback.build_failure_manifest(
            environment=callback_environment(),
            now=occurred_at,
        )
        self.assertEqual(manifest["errorCode"], "worker_workflow_failed")
        self.assertEqual(
            manifest["providerRunId"],
            "github-actions:12345678-1234-4234-8234-123456789abc",
        )
        self.assertEqual(manifest["occurredAt"], "2026-08-14T01:02:03Z")

        invalid = {**callback_environment(), "QUANT_CONTROL_CALLBACK_URL": "https://user@example.test"}
        with self.assertRaisesRegex(SystemExit, "without credentials"):
            control_callback.build_failure_manifest(environment=invalid, now=occurred_at)


if __name__ == "__main__":
    unittest.main()
