import datetime as dt
import unittest

from best_factor.calendar import rebalance_dates
from best_factor.portfolio import run_backtests


class PortfolioCalendarTest(unittest.TestCase):
    def test_monthly_and_weekly_rebalance_use_last_available_date(self):
        dates = [
            dt.date(2024, 1, 30),
            dt.date(2024, 1, 31),
            dt.date(2024, 2, 1),
            dt.date(2024, 2, 29),
            dt.date(2024, 3, 1),
        ]
        self.assertEqual(rebalance_dates(dates, "M"), [dt.date(2024, 1, 31), dt.date(2024, 2, 29), dt.date(2024, 3, 1)])
        weekly = rebalance_dates(dates, "W")
        self.assertIn(dt.date(2024, 2, 1), weekly)
        self.assertIn(dt.date(2024, 3, 1), weekly)

    def test_forward_return_uses_price_date_used_not_same_day_lookahead(self):
        prices = [
            {"ticker": "AAA", "date": dt.date(2024, 1, 31), "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "AAA", "date": dt.date(2024, 2, 29), "adj_close": 110.0, "volume": 1_000_000},
            {"ticker": "BBB", "date": dt.date(2024, 1, 31), "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "BBB", "date": dt.date(2024, 2, 29), "adj_close": 90.0, "volume": 1_000_000},
        ]
        universe = [
            {"ticker": "AAA", "market_cap": 1_000_000_000},
            {"ticker": "BBB", "market_cap": 1_000_000_000},
        ]
        scores = [
            {"factor": "test", "ticker": "AAA", "signal_date": dt.date(2024, 1, 31), "score": 1.0, "eligible": True, "skip_reason": ""},
            {"factor": "test", "ticker": "BBB", "signal_date": dt.date(2024, 1, 31), "score": 0.5, "eligible": True, "skip_reason": ""},
        ]
        result = run_backtests(prices, universe, scores, [dt.date(2024, 1, 31), dt.date(2024, 2, 29)], top_n=1)
        self.assertAlmostEqual(result["returns"][0]["return"], 0.1)
        self.assertEqual(result["holdings"][0]["price_date_used"], dt.date(2024, 1, 31))
        self.assertAlmostEqual(sum(h["weight"] for h in result["holdings"]), 1.0)

    def test_score_weighting_keeps_all_selected_holdings_positive(self):
        prices = [
            {"ticker": "AAA", "date": dt.date(2024, 1, 31), "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "AAA", "date": dt.date(2024, 2, 29), "adj_close": 110.0, "volume": 1_000_000},
            {"ticker": "BBB", "date": dt.date(2024, 1, 31), "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "BBB", "date": dt.date(2024, 2, 29), "adj_close": 105.0, "volume": 1_000_000},
            {"ticker": "CCC", "date": dt.date(2024, 1, 31), "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "CCC", "date": dt.date(2024, 2, 29), "adj_close": 101.0, "volume": 1_000_000},
        ]
        universe = [
            {"ticker": "AAA", "market_cap": 1_000_000_000},
            {"ticker": "BBB", "market_cap": 1_000_000_000},
            {"ticker": "CCC", "market_cap": 1_000_000_000},
        ]
        scores = [
            {"factor": "test", "ticker": "AAA", "signal_date": dt.date(2024, 1, 31), "score": 3.0, "eligible": True, "skip_reason": ""},
            {"factor": "test", "ticker": "BBB", "signal_date": dt.date(2024, 1, 31), "score": 2.0, "eligible": True, "skip_reason": ""},
            {"factor": "test", "ticker": "CCC", "signal_date": dt.date(2024, 1, 31), "score": 1.0, "eligible": True, "skip_reason": ""},
        ]
        result = run_backtests(prices, universe, scores, [dt.date(2024, 1, 31), dt.date(2024, 2, 29)], top_n=3, weighting="score")
        weights = [row["weight"] for row in result["holdings"]]
        self.assertEqual(len(weights), 3)
        self.assertTrue(all(weight > 0 for weight in weights))
        self.assertAlmostEqual(sum(weights), 1.0)


if __name__ == "__main__":
    unittest.main()
