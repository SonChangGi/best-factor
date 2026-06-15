import datetime as dt
import unittest

from best_factor.calendar import rebalance_dates
from best_factor.portfolio import run_backtests
from best_factor.schemas import SKIP_REASONS


class PortfolioCalendarTest(unittest.TestCase):
    def test_skip_reason_schema_includes_dynamic_missing_price_codes(self):
        self.assertIn("invalid_period_missing_price", SKIP_REASONS)
        self.assertIn("zero_coverage:<factor>", SKIP_REASONS)

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

    def test_one_way_notional_transaction_cost_charges_initial_buys_and_replacements(self):
        jan = dt.date(2024, 1, 31)
        feb = dt.date(2024, 2, 29)
        mar = dt.date(2024, 3, 31)
        prices = [
            {"ticker": "AAA", "date": jan, "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "AAA", "date": feb, "adj_close": 110.0, "volume": 1_000_000},
            {"ticker": "AAA", "date": mar, "adj_close": 110.0, "volume": 1_000_000},
            {"ticker": "BBB", "date": jan, "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "BBB", "date": feb, "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "BBB", "date": mar, "adj_close": 110.0, "volume": 1_000_000},
        ]
        universe = [
            {"ticker": "AAA", "market_cap": 1_000_000_000},
            {"ticker": "BBB", "market_cap": 1_000_000_000},
        ]
        scores = [
            {"factor": "test", "ticker": "AAA", "signal_date": jan, "score": 2.0, "eligible": True, "skip_reason": ""},
            {"factor": "test", "ticker": "BBB", "signal_date": jan, "score": 1.0, "eligible": True, "skip_reason": ""},
            {"factor": "test", "ticker": "AAA", "signal_date": feb, "score": 1.0, "eligible": True, "skip_reason": ""},
            {"factor": "test", "ticker": "BBB", "signal_date": feb, "score": 2.0, "eligible": True, "skip_reason": ""},
        ]
        result = run_backtests(
            prices,
            universe,
            scores,
            [jan, feb, mar],
            top_n=1,
            transaction_cost_bps=100,
            transaction_cost_model="one_way_notional",
        )

        returns = result["returns"]
        self.assertAlmostEqual(returns[0]["return"], 0.09)
        self.assertAlmostEqual(returns[0]["turnover"], 0.5)
        self.assertAlmostEqual(returns[1]["return"], 0.08)
        self.assertAlmostEqual(returns[1]["turnover"], 1.0)

    def test_portfolio_turnover_transaction_cost_model_preserves_legacy_cost_basis(self):
        jan = dt.date(2024, 1, 31)
        feb = dt.date(2024, 2, 29)
        prices = [
            {"ticker": "AAA", "date": jan, "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "AAA", "date": feb, "adj_close": 110.0, "volume": 1_000_000},
        ]
        universe = [{"ticker": "AAA", "market_cap": 1_000_000_000}]
        scores = [{"factor": "test", "ticker": "AAA", "signal_date": jan, "score": 1.0, "eligible": True, "skip_reason": ""}]
        result = run_backtests(
            prices,
            universe,
            scores,
            [jan, feb],
            top_n=1,
            transaction_cost_bps=100,
            transaction_cost_model="portfolio_turnover",
        )
        self.assertAlmostEqual(result["returns"][0]["return"], 0.095)

    def test_liquidity_filter_uses_configured_adv_window(self):
        jan = dt.date(2024, 1, 31)
        feb = dt.date(2024, 2, 29)
        prices = [
            {"ticker": "AAA", "date": jan, "adj_close": 100.0, "volume": 1},
            {"ticker": "AAA", "date": feb, "adj_close": 101.0, "volume": 1},
        ]
        universe = [{"ticker": "AAA", "market_cap": 1_000_000_000}]
        scores = [{"factor": "test", "ticker": "AAA", "signal_date": jan, "score": 1.0, "eligible": True, "skip_reason": ""}]

        eligible = run_backtests(prices, universe, scores, [jan, feb], top_n=1, min_dollar_volume=50, adv_window=1)
        blocked = run_backtests(prices, universe, scores, [jan, feb], top_n=1, min_dollar_volume=50, adv_window=3)

        self.assertEqual(eligible["returns"][0]["holdings_count"], 1)
        self.assertEqual(blocked["returns"][0]["holdings_count"], 0)
        self.assertIn("insufficient_volume", blocked["skipped_reasons"])

    def test_missing_selected_exit_invalidates_period_without_survivor_reweighting(self):
        prices = [
            {"ticker": "AAA", "date": dt.date(2024, 1, 31), "adj_close": 100.0, "volume": 1_000_000},
            {"ticker": "AAA", "date": dt.date(2024, 2, 29), "adj_close": 110.0, "volume": 1_000_000},
            {"ticker": "BBB", "date": dt.date(2024, 1, 31), "adj_close": 100.0, "volume": 1_000_000},
        ]
        universe = [
            {"ticker": "AAA", "market_cap": 1_000_000_000},
            {"ticker": "BBB", "market_cap": 1_000_000_000},
        ]
        scores = [
            {"factor": "test", "ticker": "AAA", "signal_date": dt.date(2024, 1, 31), "score": 2.0, "eligible": True, "skip_reason": ""},
            {"factor": "test", "ticker": "BBB", "signal_date": dt.date(2024, 1, 31), "score": 1.0, "eligible": True, "skip_reason": ""},
        ]
        result = run_backtests(prices, universe, scores, [dt.date(2024, 1, 31), dt.date(2024, 2, 29)], top_n=2)
        self.assertEqual(result["holdings"], [])
        self.assertEqual(len(result["returns"]), 1)
        self.assertEqual(result["returns"][0]["holdings_count"], 0)
        self.assertEqual(result["returns"][0]["skip_reason"], "invalid_period_missing_price")
        self.assertIn("missing_exit_price", result["skipped_reasons"])
        self.assertIn("invalid_period_missing_price", result["skipped_reasons"])
        self.assertIn("invalid_period_missing_price", SKIP_REASONS)


if __name__ == "__main__":
    unittest.main()
