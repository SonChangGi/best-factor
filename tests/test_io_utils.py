import csv
import tempfile
import unittest
from pathlib import Path

from best_factor.io_utils import write_csv_dicts


class IoUtilsTest(unittest.TestCase):
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
