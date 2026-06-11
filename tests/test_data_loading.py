import tempfile
import unittest
from pathlib import Path

from best_factor.data import adjusted_ohlc_to_adj_close, download_nasdaq_symbol_directory, load_prices_csv


class DataLoadingTest(unittest.TestCase):
    def test_adjusted_ohlc_to_adj_close_scales_raw_ohlc(self):
        open_, high, low, close = adjusted_ohlc_to_adj_close(
            open_=102.0,
            high=110.0,
            low=90.0,
            close=100.0,
            adj_close=50.0,
        )
        self.assertAlmostEqual(open_, 51.0)
        self.assertAlmostEqual(high, 55.0)
        self.assertAlmostEqual(low, 45.0)
        self.assertAlmostEqual(close, 50.0)

    def test_load_prices_csv_normalizes_ohlc_to_adjusted_close_scale(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prices.csv"
            path.write_text(
                "ticker,date,open,high,low,close,adj_close,volume\n"
                "AAA,2024-01-02,102,110,90,100,50,1000\n",
                encoding="utf-8",
            )
            row = load_prices_csv(path)[0]
        self.assertEqual(row["ticker"], "AAA")
        self.assertAlmostEqual(row["open"], 51.0)
        self.assertAlmostEqual(row["high"], 55.0)
        self.assertAlmostEqual(row["low"], 45.0)
        self.assertAlmostEqual(row["close"], 50.0)
        self.assertAlmostEqual(row["adj_close"], 50.0)

    def test_symbol_directory_download_rejects_non_nasdaq_hosts_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            for url in ["http://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt", "https://example.com/nasdaqlisted.txt"]:
                with self.subTest(url=url):
                    with self.assertRaises(ValueError):
                        download_nasdaq_symbol_directory(url, Path(tmp) / "symbols.txt")


if __name__ == "__main__":
    unittest.main()
