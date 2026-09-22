import unittest
from unittest.mock import patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".github/scripts"))
import automation_admission as gate


def run(identifier, created="2026-09-22T00:00:00Z", status="in_progress", **extra):
    return {"id": identifier, "created_at": created, "status": status,
            "html_url": f"https://github.com/runs/{identifier}", **extra}


class AdmissionTests(unittest.TestCase):
    def test_total_order_avoids_mutual_wait_and_completed_runs_do_not_block(self):
        older, newer = run(1), run(2)
        self.assertEqual(gate.blockers(older, [newer]), [])
        self.assertEqual(gate.blockers(newer, [older]), [older])
        self.assertEqual(gate.blockers(newer, [run(1, status="completed")]), [])

    def test_waits_until_earlier_pipeline_finishes_then_confirms_clear(self):
        with patch.object(gate, "api", return_value=run(2)), patch.object(
            gate, "active_peers", side_effect=[[run(1)], [], []]
        ), patch.object(gate.time, "sleep") as sleep:
            self.assertEqual(gate.wait_for_turn("SonChangGi/sox", "2", 100, 45), 0)
            self.assertEqual(sleep.call_count, 2)

    def test_timeout_does_not_grant_admission(self):
        with patch.object(gate, "api", return_value=run(2)), patch.object(
            gate, "active_peers", return_value=[run(1)]
        ):
            self.assertEqual(gate.wait_for_turn("SonChangGi/sox", "2", 0, 45), 1)

    def test_api_failure_propagates_without_admission(self):
        with patch.object(gate, "api", side_effect=OSError("unavailable")):
            with self.assertRaises(OSError):
                gate.wait_for_turn("SonChangGi/sox", "2", 100, 45)

    def test_rerun_is_ordered_by_current_attempt_start(self):
        with patch.object(gate, "api", return_value=run(1, run_attempt=2,
            run_started_at="2026-09-22T02:00:00Z")), patch.object(
            gate, "active_peers", return_value=[run(2, "2026-09-22T01:00:00Z")]
        ):
            self.assertEqual(gate.wait_for_turn("SonChangGi/sox", "1", 0, 45), 1)


if __name__ == "__main__":
    unittest.main()
