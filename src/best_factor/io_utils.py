"""Small CSV/JSON helpers to keep the project dependency-light."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_csv_dicts(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv_dicts(path: str | Path, rows: Iterable[Mapping[str, object]], fieldnames: Sequence[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: _format_value(row.get(name, "")) for name in fieldnames})


def write_json(path: str | Path, payload: object) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)
        f.write("\n")


def _format_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, float):
        if value != value:
            return ""
        return f"{value:.10g}"
    return value
