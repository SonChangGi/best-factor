import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from best_factor.data import (
    adjusted_ohlc_to_adj_close,
    download_nasdaq_symbol_directory,
    fetch_yfinance_market_caps,
    fetch_resilient_prices,
    fetch_yahoo_chart_prices,
    load_prices_csv,
    parse_nasdaq_symbol_directory,
    symbol_directory_exclusion_reason,
)


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

    def test_yahoo_chart_adapter_parses_adjusted_daily_prices(self):
        payload = _chart_payload("AAA", dt.date(2026, 6, 12), close=100.0, adj_close=50.0)
        with mock.patch("best_factor.data._download_yahoo_chart_payload", return_value=payload):
            rows, metadata = fetch_yahoo_chart_prices(["aaa"], "5d", max_workers=1)

        self.assertEqual(metadata["provider"], "yahoo_chart")
        self.assertEqual(metadata["succeeded_tickers"], ["AAA"])
        self.assertEqual(metadata["provider_fill_counts"], {"yahoo_chart": 1})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ticker"], "AAA")
        self.assertEqual(rows[0]["source"], "yahoo_chart")
        self.assertEqual(rows[0]["date"], dt.date(2026, 6, 12))
        self.assertAlmostEqual(rows[0]["open"], 51.0)
        self.assertAlmostEqual(rows[0]["high"], 55.0)
        self.assertAlmostEqual(rows[0]["low"], 45.0)
        self.assertAlmostEqual(rows[0]["close"], 50.0)

    def test_resilient_provider_fills_yfinance_missing_tickers(self):
        primary_rows = [_price_row("AAA", dt.date(2026, 6, 12), source="yfinance")]
        fallback_rows = [_price_row("BBB", dt.date(2026, 6, 12), source="yahoo_chart")]
        primary_metadata = {
            "provider": "yfinance",
            "provider_version": "test",
            "fetched_at": "2026-06-12T21:00:00Z",
            "requested_tickers": ["AAA", "BBB"],
            "requested_ticker_count": 2,
            "succeeded_tickers": ["AAA"],
            "failed_tickers": ["BBB"],
            "price_download_chunk_count": 1,
            "price_download_chunk_errors": [],
        }
        fallback_metadata = {
            "provider": "yahoo_chart",
            "provider_version": "direct-json-v8",
            "succeeded_tickers": ["BBB"],
            "failed_tickers": [],
            "price_download_request_count": 1,
            "price_download_chunk_errors": [],
        }

        with (
            mock.patch("best_factor.data.fetch_yfinance_prices", return_value=(primary_rows, primary_metadata)),
            mock.patch("best_factor.data.fetch_yahoo_chart_prices", return_value=(fallback_rows, fallback_metadata)),
        ):
            rows, metadata = fetch_resilient_prices(["AAA", "BBB"], "5d")

        self.assertEqual([row["ticker"] for row in rows], ["AAA", "BBB"])
        self.assertEqual(metadata["provider"], "yfinance_yahoo_chart")
        self.assertEqual(metadata["succeeded_tickers"], ["AAA", "BBB"])
        self.assertEqual(metadata["failed_tickers"], [])
        self.assertEqual(metadata["provider_attempted_sources"], ["yfinance", "yahoo_chart"])
        self.assertEqual(metadata["provider_fill_counts"], {"yfinance": 1, "yahoo_chart": 1})
        self.assertEqual(metadata["fallback_filled_ticker_count"], 1)
        self.assertEqual(metadata["fallback_filled_tickers"], ["BBB"])

    def test_market_cap_screener_paginates_and_uses_bounded_targeted_fallback(self):
        fake_yfinance = mock.Mock()
        fake_yfinance.EquityQuery.side_effect = lambda operator, operand: (operator, operand)
        fake_yfinance.screen.side_effect = [
            {
                "start": 0,
                "count": 2,
                "total": 3,
                "quotes": [
                    {
                        "symbol": "AAA",
                        "quoteType": "EQUITY",
                        "currency": "USD",
                        "marketCap": 12_000_000_000,
                        "regularMarketTime": 1_784_923_200,
                    },
                    {
                        "symbol": "AAZ",
                        "quoteType": "EQUITY",
                        "currency": "USD",
                        "marketCap": 1_000_000_000,
                        "regularMarketTime": 1_784_923_200,
                    },
                ],
            },
            {
                "start": 2,
                "count": 1,
                "total": 3,
                "quotes": [
                    {
                        "symbol": "BBB",
                        "quoteType": "EQUITY",
                        "currency": "USD",
                        "marketCap": 8_000_000_000,
                        "regularMarketTime": 1_784_923_201,
                    }
                ],
            },
        ]
        fake_yfinance.Ticker.return_value.fast_info = {"market_cap": 4_000_000_000}
        fake_yfinance.Ticker.return_value.info = {}

        with mock.patch.dict(sys.modules, {"yfinance": fake_yfinance}):
            market_caps, metadata = fetch_yfinance_market_caps(
                ["AAA", "BBB", "CCC"],
                page_size=2,
                max_results=10,
                max_targeted_fallbacks=1,
            )

        self.assertEqual(
            market_caps,
            {
                "AAA": 12_000_000_000,
                "BBB": 8_000_000_000,
                "CCC": 4_000_000_000,
            },
        )
        self.assertEqual(metadata["matched_ticker_count"], 3)
        self.assertEqual(metadata["coverage_ratio"], 1.0)
        self.assertEqual(metadata["screener_page_count"], 2)
        self.assertEqual(metadata["screener_snapshot_attempt_count"], 1)
        self.assertEqual(metadata["screener_snapshot_retry_count"], 0)
        self.assertEqual(metadata["screener_snapshot_retry_errors"], [])
        self.assertEqual(metadata["targeted_fallback_count"], 1)
        self.assertEqual(metadata["missing_tickers"], [])
        fake_yfinance.Ticker.assert_called_once_with("CCC")

    def test_market_cap_screener_uses_exact_us_equity_query(self):
        fake_yfinance = mock.Mock()
        fake_yfinance.EquityQuery.side_effect = lambda operator, operand: (operator, operand)
        fake_yfinance.screen.return_value = {
            "start": 0,
            "count": 0,
            "total": 0,
            "quotes": [],
        }
        expected_exchange_query = (
            "is-in",
            ["exchange", "NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS", "CXI", "NAE", "YHD"],
        )
        expected_query = (
            "and",
            [
                ("eq", ["region", "us"]),
                expected_exchange_query,
                ("gt", ["intradaymarketcap", 0]),
            ],
        )

        with mock.patch.dict(sys.modules, {"yfinance": fake_yfinance}):
            fetch_yfinance_market_caps(
                ["AAA"],
                page_size=1,
                max_results=1,
                max_targeted_fallbacks=0,
            )

        self.assertEqual(
            fake_yfinance.EquityQuery.call_args_list,
            [
                mock.call("eq", ["region", "us"]),
                mock.call("is-in", expected_exchange_query[1]),
                mock.call("gt", ["intradaymarketcap", 0]),
                mock.call("and", expected_query[1]),
            ],
        )
        fake_yfinance.screen.assert_called_once_with(
            expected_query,
            offset=0,
            size=1,
            sortField="ticker",
            sortAsc=True,
        )

    def test_market_cap_screener_excludes_non_usd_and_non_equity_quotes(self):
        fake_yfinance = mock.Mock()
        fake_yfinance.EquityQuery.side_effect = lambda operator, operand: (operator, operand)
        fake_yfinance.screen.return_value = {
            "start": 0,
            "count": 2,
            "total": 2,
            "quotes": [
                {
                    "symbol": "AAA",
                    "quoteType": "EQUITY",
                    "currency": "CAD",
                    "marketCap": 12_000_000_000,
                },
                {
                    "symbol": "BBB",
                    "quoteType": "ETF",
                    "currency": "USD",
                    "marketCap": 8_000_000_000,
                },
            ],
        }

        with mock.patch.dict(sys.modules, {"yfinance": fake_yfinance}):
            market_caps, metadata = fetch_yfinance_market_caps(
                ["AAA", "BBB"],
                page_size=2,
                max_results=2,
                max_targeted_fallbacks=0,
            )

        self.assertEqual(market_caps, {})
        self.assertEqual(metadata["matched_ticker_count"], 0)
        self.assertEqual(metadata["missing_tickers"], ["AAA", "BBB"])
        fake_yfinance.Ticker.assert_not_called()

    def test_market_cap_screener_rejects_duplicate_order_start_and_count_drift(self):
        cases = [
            (
                "duplicate",
                {
                    "start": 0,
                    "count": 2,
                    "total": 2,
                    "quotes": [
                        {"symbol": "AAA", "quoteType": "EQUITY", "currency": "USD", "marketCap": 1},
                        {"symbol": "AAA", "quoteType": "EQUITY", "currency": "USD", "marketCap": 1},
                    ],
                },
                "duplicate symbol",
            ),
            (
                "order",
                {
                    "start": 0,
                    "count": 2,
                    "total": 2,
                    "quotes": [
                        {"symbol": "BBB", "quoteType": "EQUITY", "currency": "USD", "marketCap": 1},
                        {"symbol": "AAA", "quoteType": "EQUITY", "currency": "USD", "marketCap": 1},
                    ],
                },
                "ticker order drifted",
            ),
            (
                "start",
                {
                    "start": 1,
                    "count": 1,
                    "total": 1,
                    "quotes": [
                        {"symbol": "AAA", "quoteType": "EQUITY", "currency": "USD", "marketCap": 1},
                    ],
                },
                "start drifted",
            ),
            (
                "count",
                {
                    "start": 0,
                    "count": 2,
                    "total": 1,
                    "quotes": [
                        {"symbol": "AAA", "quoteType": "EQUITY", "currency": "USD", "marketCap": 1},
                    ],
                },
                "count mismatch",
            ),
        ]

        for name, response, error_pattern in cases:
            with self.subTest(name=name):
                fake_yfinance = mock.Mock()
                fake_yfinance.EquityQuery.side_effect = lambda operator, operand: (operator, operand)
                fake_yfinance.screen.return_value = response
                with mock.patch.dict(sys.modules, {"yfinance": fake_yfinance}):
                    with self.assertRaisesRegex(ValueError, error_pattern):
                        fetch_yfinance_market_caps(
                            ["AAA", "BBB"],
                            page_size=2,
                            max_results=2,
                            max_targeted_fallbacks=0,
                        )

    def test_market_cap_screener_skips_targeted_fallback_above_25_unresolved(self):
        fake_yfinance = mock.Mock()
        fake_yfinance.EquityQuery.side_effect = lambda operator, operand: (operator, operand)
        fake_yfinance.screen.return_value = {
            "start": 0,
            "count": 0,
            "total": 0,
            "quotes": [],
        }
        requested = [f"SYM{index:02d}" for index in range(26)]

        with mock.patch.dict(sys.modules, {"yfinance": fake_yfinance}):
            market_caps, metadata = fetch_yfinance_market_caps(requested)

        self.assertEqual(market_caps, {})
        self.assertEqual(metadata["targeted_fallback_count"], 0)
        self.assertEqual(metadata["missing_tickers"], requested)
        fake_yfinance.Ticker.assert_not_called()

    def test_market_cap_screener_rejects_result_sets_above_guard(self):
        fake_yfinance = mock.Mock()
        fake_yfinance.EquityQuery.side_effect = lambda operator, operand: (operator, operand)
        fake_yfinance.screen.return_value = {
            "start": 0,
            "count": 1,
            "total": 11,
            "quotes": [
                {
                    "symbol": "AAA",
                    "quoteType": "EQUITY",
                    "currency": "USD",
                    "marketCap": 12_000_000_000,
                }
            ],
        }
        with mock.patch.dict(sys.modules, {"yfinance": fake_yfinance}):
            with self.assertRaisesRegex(ValueError, "exceeds max_results"):
                fetch_yfinance_market_caps(["AAA"], page_size=1, max_results=10)

    def test_market_cap_screener_restarts_the_whole_snapshot_after_total_drift(self):
        fake_yfinance = mock.Mock()
        fake_yfinance.EquityQuery.side_effect = lambda operator, operand: (operator, operand)
        fake_yfinance.screen.side_effect = [
            {
                "start": 0,
                "count": 1,
                "total": 2,
                "quotes": [
                    {
                        "symbol": "AAA",
                        "quoteType": "EQUITY",
                        "currency": "USD",
                        "marketCap": 12_000_000_000,
                    }
                ],
            },
            {
                "start": 1,
                "count": 1,
                "total": 3,
                "quotes": [
                    {
                        "symbol": "BBB",
                        "quoteType": "EQUITY",
                        "currency": "USD",
                        "marketCap": 8_000_000_000,
                    }
                ],
            },
            {
                "start": 0,
                "count": 1,
                "total": 2,
                "quotes": [
                    {
                        "symbol": "AAA",
                        "quoteType": "EQUITY",
                        "currency": "USD",
                        "marketCap": 12_000_000_000,
                    }
                ],
            },
            {
                "start": 1,
                "count": 1,
                "total": 2,
                "quotes": [
                    {
                        "symbol": "BBB",
                        "quoteType": "EQUITY",
                        "currency": "USD",
                        "marketCap": 8_000_000_000,
                    }
                ],
            },
        ]
        with mock.patch.dict(sys.modules, {"yfinance": fake_yfinance}):
            market_caps, metadata = fetch_yfinance_market_caps(
                ["AAA", "BBB"],
                page_size=1,
                max_results=10,
                snapshot_attempts=2,
                snapshot_initial_delay=0,
            )

        self.assertEqual(market_caps, {"AAA": 12_000_000_000, "BBB": 8_000_000_000})
        self.assertEqual(metadata["screener_snapshot_attempt_count"], 2)
        self.assertEqual(metadata["screener_snapshot_retry_count"], 1)
        self.assertEqual(metadata["screener_snapshot_retry_errors"][0]["attempt"], 1)
        self.assertIn("total drifted", metadata["screener_snapshot_retry_errors"][0]["message"])
        self.assertEqual(fake_yfinance.screen.call_count, 4)

    def test_market_cap_screener_fails_closed_after_bounded_total_drift_retries(self):
        fake_yfinance = mock.Mock()
        fake_yfinance.EquityQuery.side_effect = lambda operator, operand: (operator, operand)
        drifting_pair = [
            {
                "start": 0,
                "count": 1,
                "total": 2,
                "quotes": [
                    {
                        "symbol": "AAA",
                        "quoteType": "EQUITY",
                        "currency": "USD",
                        "marketCap": 12_000_000_000,
                    }
                ],
            },
            {
                "start": 1,
                "count": 1,
                "total": 3,
                "quotes": [
                    {
                        "symbol": "BBB",
                        "quoteType": "EQUITY",
                        "currency": "USD",
                        "marketCap": 8_000_000_000,
                    }
                ],
            },
        ]
        fake_yfinance.screen.side_effect = drifting_pair * 3

        with mock.patch.dict(sys.modules, {"yfinance": fake_yfinance}):
            with self.assertRaisesRegex(ValueError, "unstable after 3 snapshot attempts"):
                fetch_yfinance_market_caps(
                    ["AAA", "BBB"],
                    page_size=1,
                    max_results=10,
                    snapshot_attempts=3,
                    snapshot_initial_delay=0,
                )

        self.assertEqual(fake_yfinance.screen.call_count, 6)

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


def _chart_payload(ticker: str, date: dt.date, *, close: float, adj_close: float) -> dict[str, object]:
    timestamp = int(dt.datetime(date.year, date.month, date.day, 20, 0, tzinfo=dt.UTC).timestamp())
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": ticker},
                    "timestamp": [timestamp],
                    "indicators": {
                        "quote": [
                            {
                                "open": [102.0],
                                "high": [110.0],
                                "low": [90.0],
                                "close": [close],
                                "volume": [1234],
                            }
                        ],
                        "adjclose": [{"adjclose": [adj_close]}],
                    },
                }
            ],
            "error": None,
        }
    }


def _price_row(ticker: str, date: dt.date, *, source: str) -> dict[str, object]:
    return {
        "ticker": ticker,
        "date": date,
        "open": 10.0,
        "high": 11.0,
        "low": 9.0,
        "close": 10.0,
        "adj_close": 10.0,
        "volume": 1000,
        "source": source,
        "fetched_at": "2026-06-12T21:00:00Z",
    }


if __name__ == "__main__":
    unittest.main()
