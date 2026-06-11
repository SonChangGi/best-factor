import tempfile
import unittest
from pathlib import Path

from best_factor.data import adjusted_ohlc_to_adj_close, download_nasdaq_symbol_directory, load_prices_csv, parse_nasdaq_symbol_directory, symbol_directory_exclusion_reason


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


    def test_nasdaq_symbol_directory_parser_keeps_only_conservative_common_stock(self):
        text = (
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
            "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N\n"
            "ETFA|Example ETF|G|N|N|100|Y|N\n"
            "TST|NASDAQ TEST STOCK|Q|Y|N|100|N|N\n"
            "BADP|Bad Co - Preferred Stock|Q|N|N|100|N|N\n"
            "BADW|Bad Co - Warrant|Q|N|N|100|N|N\n"
            "BADU|Bad Co - Units|Q|N|N|100|N|N\n"
            "ADRX|Foreign Co - American Depositary Shares|Q|N|N|100|N|N\n"
            "ORDS|Foreign Co - Ordinary Shares|Q|N|N|100|N|N\n"
            "DEFN|Deficient Co - Common Stock|Q|N|D|100|N|N\n"
            "File Creation Time: 0611202600:00|||||||\n"
        )
        rows, metadata = parse_nasdaq_symbol_directory(text, source_url="https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt")
        self.assertEqual([row["ticker"] for row in rows], ["AAPL"])
        self.assertEqual(metadata["raw_symbol_count"], 9)
        self.assertEqual(metadata["common_stock_candidate_count"], 1)
        excluded = metadata["excluded_symbol_counts"]
        for reason in ["etf", "test_issue", "preferred", "warrant", "unit", "non_normal_financial_status"]:
            self.assertIn(reason, excluded)

    def test_symbol_directory_exclusion_rejects_benchmarks_and_unsupported_formats(self):
        self.assertEqual(symbol_directory_exclusion_reason({"Symbol": "QQQ", "Security Name": "Invesco QQQ Trust", "ETF": "Y", "Test Issue": "N"}), "benchmark_or_blank")
        self.assertEqual(symbol_directory_exclusion_reason({"Symbol": "BRK.B", "Security Name": "Berkshire Hathaway Inc. Common Stock", "ETF": "N", "Test Issue": "N"}), "unsupported_symbol_format")

    def test_symbol_directory_download_rejects_non_nasdaq_hosts_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            for url in ["http://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt", "https://example.com/nasdaqlisted.txt"]:
                with self.subTest(url=url):
                    with self.assertRaises(ValueError):
                        download_nasdaq_symbol_directory(url, Path(tmp) / "symbols.txt")


if __name__ == "__main__":
    unittest.main()
