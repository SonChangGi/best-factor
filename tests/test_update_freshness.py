import datetime as dt
import importlib.util
import json
import tempfile
import unittest
import sys
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check_dashboard_freshness.py"

spec = importlib.util.spec_from_file_location("check_dashboard_freshness", SCRIPT)
freshness = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(freshness)


class DashboardFreshnessTest(unittest.TestCase):
    def test_primary_also_skips_current_completed_session(self):
        path = self.write_payload(generated_at="2026-06-10T22:00:00Z", data_end_date="2026-06-10")
        result = freshness.decide_update(event_name="schedule", event_schedule="43 23 * * 1-5",
            now_utc=dt.datetime(2026, 6, 10, 23, 43, tzinfo=dt.UTC), json_file=path)
        self.assertEqual(result["should_update"], "false")

    def test_manual_or_push_events_always_update(self):
        result = freshness.decide_update(
            event_name="workflow_dispatch",
            event_schedule="",
            now_utc=dt.datetime(2026, 6, 11, 2, 0, tzinfo=dt.UTC),
            live_url="https://example.invalid/not-used.json",
        )
        self.assertEqual(result["should_update"], "true")
        self.assertEqual(result["freshness_reason"], "manual_or_push_event_always_refreshes")

    def test_nine_kst_fallback_skips_when_public_json_is_current(self):
        path = self.write_payload(generated_at="2026-06-11T00:20:00Z", data_end_date="2026-06-10")
        result = freshness.decide_update(
            event_name="schedule",
            event_schedule="13 3 * * 2-6",
            now_utc=dt.datetime(2026, 6, 11, 0, 0, tzinfo=dt.UTC),
            json_file=path,
        )
        self.assertEqual(result["should_update"], "false")
        self.assertEqual(result["freshness_reason"], "fresh_for_expected_completed_us_session")
        self.assertEqual(result["actual_data_end_date"], "2026-06-10")

    def test_nine_kst_fallback_reruns_when_data_end_is_stale(self):
        path = self.write_payload(generated_at="2026-06-11T00:20:00Z", data_end_date="2026-06-09")
        result = freshness.decide_update(
            event_name="schedule",
            event_schedule="13 3 * * 2-6",
            now_utc=dt.datetime(2026, 6, 11, 0, 0, tzinfo=dt.UTC),
            json_file=path,
        )
        self.assertEqual(result["should_update"], "true")
        self.assertEqual(result["freshness_reason"], "stale_data_end_before_expected_us_session")

    def test_every_fallback_schedule_skips_current_and_reruns_stale_data(self):
        for schedule in freshness.DEFAULT_FALLBACK_CRONS:
            hour_utc = int(schedule.split()[1])
            now_utc = dt.datetime(2026, 6, 11, hour_utc, 0, tzinfo=dt.UTC)
            with self.subTest(schedule=schedule, payload="current"):
                current_path = self.write_payload(generated_at="2026-06-11T00:20:00Z", data_end_date="2026-06-10")
                current = freshness.decide_update(
                    event_name="schedule",
                    event_schedule=schedule,
                    now_utc=now_utc,
                    json_file=current_path,
                )
                self.assertEqual(current["should_update"], "false")
                self.assertEqual(current["freshness_reason"], "fresh_for_expected_completed_us_session")
            with self.subTest(schedule=schedule, payload="stale_data_end"):
                stale_path = self.write_payload(generated_at="2026-06-11T00:20:00Z", data_end_date="2026-06-09")
                stale = freshness.decide_update(
                    event_name="schedule",
                    event_schedule=schedule,
                    now_utc=now_utc,
                    json_file=stale_path,
                )
                self.assertEqual(stale["should_update"], "true")
                self.assertEqual(stale["freshness_reason"], "stale_data_end_before_expected_us_session")

    def test_fallback_skips_current_session_even_when_generation_is_yesterday_kst(self):
        path = self.write_payload(generated_at="2026-06-10T12:00:00Z", data_end_date="2026-06-10")
        result = freshness.decide_update(
            event_name="schedule",
            event_schedule="13 3 * * 2-6",
            now_utc=dt.datetime(2026, 6, 11, 0, 0, tzinfo=dt.UTC),
            json_file=path,
        )
        self.assertEqual(result["should_update"], "false")
        self.assertEqual(result["freshness_reason"], "fresh_for_expected_completed_us_session")

    def test_fallback_reruns_when_public_json_is_missing_or_broken(self):
        result = freshness.decide_update(
            event_name="schedule",
            event_schedule="43 6 * * 2-6",
            now_utc=dt.datetime(2026, 6, 11, 4, 0, tzinfo=dt.UTC),
            json_file=Path("/tmp/definitely-missing-best-factor.json"),
        )
        self.assertEqual(result["should_update"], "true")
        self.assertTrue(result["freshness_reason"].startswith("freshness_check_failed:"), result)

    def test_expected_us_session_skips_weekends(self):
        # 2026-06-14 10:00 KST is Sunday; latest expected US regular session is Friday 2026-06-12.
        expected = freshness.latest_expected_us_session_date(dt.datetime(2026, 6, 14, 1, 0, tzinfo=dt.UTC))
        self.assertEqual(expected.isoformat(), "2026-06-12")

    def test_calendar_holiday_dst_intraday_and_new_year(self):
        cases = {
            "2026-09-22T00:00:00+00:00": "2026-09-21",
            "2026-09-21T19:59:00+00:00": "2026-09-18",
            "2026-09-07T23:00:00+00:00": "2026-09-04",
            "2026-11-27T17:59:00+00:00": "2026-11-25",
            "2026-11-27T18:01:00+00:00": "2026-11-27",
            "2021-12-31T22:00:00+00:00": "2021-12-31",
            "2025-01-09T23:00:00+00:00": "2025-01-08",
        }
        for timestamp, expected in cases.items():
            with self.subTest(timestamp=timestamp):
                self.assertEqual(freshness.latest_expected_us_session_date(dt.datetime.fromisoformat(timestamp)).isoformat(), expected)

    def test_default_manual_reuses_only_matching_configuration_and_result_binding(self):
        sys.path.insert(0, str(SCRIPT.parent))
        payload = json.loads((ROOT / "docs/data/latest-results.json").read_text())
        config = json.loads((ROOT / "docs/data/dashboard-config.json").read_text())
        completed = dt.datetime.combine(dt.date.fromisoformat(payload["summary"]["data_end_date"]), dt.time(23), dt.UTC)
        with mock.patch.object(freshness, "load_payload", side_effect=[payload, config]):
            result = freshness.decide_update(event_name="workflow_dispatch", event_schedule="",
                now_utc=completed, reuse_current_manual=True,
                config_json=ROOT / ".github/best-factor-dashboard-config.json")
        self.assertEqual(result["should_update"], "false")
        changed = {**config, "result_binding": {**config["result_binding"], "source_hash": "0"*16}}
        with mock.patch.object(freshness, "load_payload", side_effect=[payload, changed]):
            result = freshness.decide_update(event_name="workflow_dispatch", event_schedule="",
                now_utc=completed, reuse_current_manual=True,
                config_json=ROOT / ".github/best-factor-dashboard-config.json")
        self.assertEqual(result["should_update"], "true")
        self.assertEqual(result["freshness_reason"], "configuration_or_result_binding_changed")

    def write_payload(self, *, generated_at: str, data_end_date: str) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False)
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        json.dump({"generated_at": generated_at, "summary": {"data_end_date": data_end_date}}, tmp)
        tmp.close()
        return Path(tmp.name)


if __name__ == "__main__":
    unittest.main()
