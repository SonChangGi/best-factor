import csv
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from best_factor.io_utils import write_csv_dicts, write_json


class IoUtilsTest(unittest.TestCase):
    def test_json_writer_serializes_date_valued_run_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.json"
            write_json(path, {"expected_data_end_date": dt.date(2026, 9, 21)})
            self.assertEqual(json.loads(path.read_text()), {"expected_data_end_date": "2026-09-21"})

    def test_csv_writer_neutralizes_spreadsheet_formula_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            write_csv_dicts(
                path,
                [
                    {"ticker": "=CMD()", "reason": "+SUM(1,1)", "numeric": -0.25},
                    {"ticker": "@evil", "reason": "-text", "numeric": 1.0},
                ],
                ["ticker", "reason", "numeric"],
            )
            with path.open(newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))

        self.assertEqual(rows[0]["ticker"], "'=CMD()")
        self.assertEqual(rows[0]["reason"], "'+SUM(1,1)")
        self.assertEqual(rows[0]["numeric"], "-0.25")
        self.assertEqual(rows[1]["ticker"], "'@evil")
        self.assertEqual(rows[1]["reason"], "'-text")


if __name__ == "__main__":
    unittest.main()
