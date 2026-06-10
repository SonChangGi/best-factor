"""Rebalance calendar helpers."""
from __future__ import annotations

import datetime as dt


def rebalance_dates(dates: list[dt.date], frequency: str) -> list[dt.date]:
    if frequency not in {"M", "W"}:
        raise ValueError("rebalance frequency must be 'M' or 'W'")
    if not dates:
        return []
    dates = sorted(set(dates))
    buckets: dict[tuple[int, int], dt.date] = {}
    for date in dates:
        if frequency == "M":
            key = (date.year, date.month)
        else:
            iso = date.isocalendar()
            key = (iso.year, iso.week)
        buckets[key] = date
    return sorted(buckets.values())
