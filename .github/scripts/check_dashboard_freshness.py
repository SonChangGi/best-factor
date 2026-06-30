#!/usr/bin/env python3
"""Decide whether a scheduled fallback run should regenerate the dashboard.

GitHub Actions schedules are UTC. The public dashboard's business contract is
Korea-time freshness: a staggered primary Tue-Sat run at 07:00 KST should
publish the latest closed US regular session, while fallback checks at
09:00/11:00/13:00 KST rerun only if the already deployed JSON is stale or
missing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_LIVE_URL = "https://sonchanggi.github.io/best-factor/data/latest-results.json"
DEFAULT_PRIMARY_CRONS = ("0 22 * * 1-5",)
DEFAULT_FALLBACK_CRONS = ("0 0 * * 2-6", "0 2 * * 2-6", "0 4 * * 2-6")
DEFAULT_TIMEZONE = "Asia/Seoul"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-name", default=os.getenv("GITHUB_EVENT_NAME", ""))
    parser.add_argument("--event-schedule", default=os.getenv("GITHUB_EVENT_SCHEDULE", ""))
    parser.add_argument("--live-url", default=DEFAULT_LIVE_URL)
    parser.add_argument("--json-file", type=Path, help="Read dashboard JSON from a local file instead of --live-url")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--primary-cron", action="append", default=[])
    parser.add_argument("--fallback-cron", action="append", default=[])
    parser.add_argument("--now", help="ISO timestamp for deterministic tests, e.g. 2026-06-11T01:00:00Z")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    primary_crons = tuple(args.primary_cron or DEFAULT_PRIMARY_CRONS)
    fallback_crons = tuple(args.fallback_cron or DEFAULT_FALLBACK_CRONS)
    now = parse_datetime(args.now) if args.now else dt.datetime.now(dt.UTC)

    result = decide_update(
        event_name=args.event_name,
        event_schedule=args.event_schedule,
        primary_crons=primary_crons,
        fallback_crons=fallback_crons,
        now_utc=now,
        timezone=args.timezone,
        json_file=args.json_file,
        live_url=args.live_url,
    )
    write_github_output(result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def decide_update(
    *,
    event_name: str,
    event_schedule: str,
    primary_crons: tuple[str, ...] = DEFAULT_PRIMARY_CRONS,
    fallback_crons: tuple[str, ...] = DEFAULT_FALLBACK_CRONS,
    now_utc: dt.datetime | None = None,
    timezone: str = DEFAULT_TIMEZONE,
    json_file: Path | None = None,
    live_url: str = DEFAULT_LIVE_URL,
) -> dict[str, str]:
    """Return GitHub-output-safe strings describing whether to update."""
    now_utc = ensure_utc(now_utc or dt.datetime.now(dt.UTC))
    schedule = (event_schedule or "").strip()
    event = (event_name or "").strip()
    expected = latest_expected_us_session_date(now_utc, timezone)

    base = {
        "event_name": event or "unknown",
        "event_schedule": schedule or "none",
        "expected_data_end_date": expected.isoformat(),
        "timezone": timezone,
    }

    if event != "schedule":
        return {**base, "should_update": "true", "freshness_reason": "manual_or_push_event_always_refreshes"}
    if schedule in primary_crons:
        return {**base, "should_update": "true", "freshness_reason": "primary_07_kst_schedule_always_refreshes"}
    if schedule not in fallback_crons:
        return {**base, "should_update": "true", "freshness_reason": "unknown_schedule_refreshes_conservatively"}

    try:
        payload = load_payload(json_file=json_file, live_url=live_url)
        freshness = evaluate_payload_freshness(payload, now_utc=now_utc, timezone=timezone)
    except Exception as exc:  # noqa: BLE001 - fallback should repair missing/broken public JSON.
        return {
            **base,
            "should_update": "true",
            "freshness_reason": f"freshness_check_failed:{type(exc).__name__}",
            "actual_data_end_date": "unknown",
            "actual_generated_kst_date": "unknown",
        }

    should_update = not freshness["fresh"]
    return {
        **base,
        "should_update": "true" if should_update else "false",
        "freshness_reason": freshness["reason"],
        "actual_data_end_date": freshness["actual_data_end_date"],
        "actual_generated_kst_date": freshness["actual_generated_kst_date"],
    }


def evaluate_payload_freshness(payload: dict[str, Any], *, now_utc: dt.datetime, timezone: str) -> dict[str, Any]:
    expected = latest_expected_us_session_date(now_utc, timezone)
    local_today = ensure_utc(now_utc).astimezone(ZoneInfo(timezone)).date()
    generated_at = parse_datetime(str(payload.get("generated_at") or ""))
    generated_local_date = generated_at.astimezone(ZoneInfo(timezone)).date()
    data_end = payload_data_end_date(payload)

    if generated_local_date < local_today:
        return {
            "fresh": False,
            "reason": "stale_generated_at_not_today_kst",
            "actual_data_end_date": data_end.isoformat(),
            "actual_generated_kst_date": generated_local_date.isoformat(),
        }
    if data_end < expected:
        return {
            "fresh": False,
            "reason": "stale_data_end_before_expected_us_session",
            "actual_data_end_date": data_end.isoformat(),
            "actual_generated_kst_date": generated_local_date.isoformat(),
        }
    return {
        "fresh": True,
        "reason": "fresh_for_kst_today_and_expected_us_session",
        "actual_data_end_date": data_end.isoformat(),
        "actual_generated_kst_date": generated_local_date.isoformat(),
    }


def load_payload(*, json_file: Path | None, live_url: str) -> dict[str, Any]:
    if json_file is not None:
        raw = json_file.read_text(encoding="utf-8")
    else:
        request = urllib.request.Request(live_url, headers={"Cache-Control": "no-cache", "User-Agent": "best-factor-freshness/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - repository-owned HTTPS URL by default.
            raw = response.read().decode("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("dashboard JSON must be an object")
    return payload


def payload_data_end_date(payload: dict[str, Any]) -> dt.date:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    raw = summary.get("data_end_date") or metadata.get("data_end_date")
    if not raw:
        raise ValueError("missing data_end_date")
    return dt.date.fromisoformat(str(raw))


def latest_expected_us_session_date(now_utc: dt.datetime, timezone: str = DEFAULT_TIMEZONE) -> dt.date:
    """Latest US regular-session date expected to be available by KST morning."""
    local_today = ensure_utc(now_utc).astimezone(ZoneInfo(timezone)).date()
    candidate = local_today - dt.timedelta(days=1)
    while not is_us_market_trading_day(candidate):
        candidate -= dt.timedelta(days=1)
    return candidate


def is_us_market_trading_day(day: dt.date) -> bool:
    if day.weekday() >= 5:
        return False
    holidays = set()
    for year in (day.year - 1, day.year, day.year + 1):
        holidays.update(nyse_holidays(year))
    return day not in holidays


def nyse_holidays(year: int) -> set[dt.date]:
    """Best-effort NYSE full-day holidays without external dependencies."""
    holidays = {
        observed_fixed(year, 1, 1),  # New Year's Day
        nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        nth_weekday(year, 2, 0, 3),  # Washington's Birthday / Presidents Day
        easter_sunday(year) - dt.timedelta(days=2),  # Good Friday
        last_weekday(year, 5, 0),  # Memorial Day
        observed_fixed(year, 6, 19),  # Juneteenth
        observed_fixed(year, 7, 4),  # Independence Day
        nth_weekday(year, 9, 0, 1),  # Labor Day
        nth_weekday(year, 11, 3, 4),  # Thanksgiving Day
        observed_fixed(year, 12, 25),  # Christmas Day
    }
    # Juneteenth became a US exchange holiday in 2022.
    if year < 2022:
        holidays.discard(observed_fixed(year, 6, 19))
    return holidays


def observed_fixed(year: int, month: int, day: int) -> dt.date:
    actual = dt.date(year, month, day)
    if actual.weekday() == 5:
        return actual - dt.timedelta(days=1)
    if actual.weekday() == 6:
        return actual + dt.timedelta(days=1)
    return actual


def nth_weekday(year: int, month: int, weekday: int, nth: int) -> dt.date:
    day = dt.date(year, month, 1)
    while day.weekday() != weekday:
        day += dt.timedelta(days=1)
    return day + dt.timedelta(days=7 * (nth - 1))


def last_weekday(year: int, month: int, weekday: int) -> dt.date:
    if month == 12:
        day = dt.date(year + 1, 1, 1) - dt.timedelta(days=1)
    else:
        day = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    while day.weekday() != weekday:
        day -= dt.timedelta(days=1)
    return day


def easter_sunday(year: int) -> dt.date:
    """Gregorian Easter date using Meeus/Jones/Butcher algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(year, month, day)


def parse_datetime(value: str) -> dt.datetime:
    if not value:
        raise ValueError("missing datetime")
    normalized = value.replace("Z", "+00:00")
    parsed = dt.datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return ensure_utc(parsed)


def ensure_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


def write_github_output(result: dict[str, str]) -> None:
    output = os.getenv("GITHUB_OUTPUT")
    if not output:
        return
    allowed = {
        "should_update",
        "freshness_reason",
        "expected_data_end_date",
        "actual_data_end_date",
        "actual_generated_kst_date",
        "event_name",
        "event_schedule",
    }
    with open(output, "a", encoding="utf-8") as fh:
        for key in allowed:
            if key in result:
                value = str(result[key]).replace("\n", " ")
                fh.write(f"{key}={value}\n")


if __name__ == "__main__":
    raise SystemExit(main())
