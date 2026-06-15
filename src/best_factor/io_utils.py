"""Small CSV/JSON helpers to keep the project dependency-light."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

SPREADSHEET_DANGEROUS_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


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
    if isinstance(value, str):
        return _escape_spreadsheet_formula(value)
    return value


def _escape_spreadsheet_formula(value: str) -> str:
    """Neutralize values that spreadsheet apps may execute as formulas.

    The project emits CSV artifacts that users may open in Excel, Numbers,
    or Google Sheets.  A literal ticker/name/reason beginning with formula
    metacharacters should stay text, not become a formula.  Numeric Python
    values are formatted before this branch, so legitimate negative numbers
    produced by the code are not changed.
    """
    if value and value[0] in SPREADSHEET_DANGEROUS_PREFIXES:
        return "'" + value
    return value
