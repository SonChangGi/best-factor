import math
import unittest

from best_factor.metrics import compute_metrics, max_drawdown
from best_factor.ranking import rank_factors


class MetricsRankingTest(unittest.TestCase):
    def test_max_drawdown(self):
        self.assertAlmostEqual(max_drawdown([1.0, 1.2, 0.9, 1.3]), -0.25)

    def test_compute_metrics_contains_required_fields(self):
        rows = [
            {"factor": "a", "period_end": i, "return": r, "turnover": 0.1, "holdings_count": 2}
            for i, r in enumerate([0.02, -0.01, 0.03, 0.01], start=1)
        ]
        result = compute_metrics(rows, "M")[0]
        for key in ["cagr", "annual_return", "volatility", "sharpe", "sortino", "calmar", "max_drawdown", "coverage"]:
            self.assertIn(key, result)
        self.assertLessEqual(result["max_drawdown"], 0)

    def test_ranking_handles_nan_inf_equal_and_single_factor(self):
        single = rank_factors([
            {"factor": "only", "cagr": 0.1, "annual_return": 0.1, "volatility": 0.2, "sharpe": 1.0, "sortino": math.inf, "calmar": 0.5, "max_drawdown": -0.2, "turnover": 0.1, "coverage": 1.0, "composite_score": 0.0}
        ])
        self.assertEqual(single[0]["factor"], "only")
        self.assertTrue(math.isfinite(single[0]["composite_score"]))

    def test_tie_break_order_is_deterministic(self):
        ranked = rank_factors([
            {"factor": "z_factor", "cagr": 0.1, "annual_return": 0.1, "volatility": 0.2, "sharpe": 1.0, "sortino": 1.0, "calmar": 1.0, "max_drawdown": -0.2, "turnover": 0.1, "coverage": 1.0, "composite_score": 0.0},
            {"factor": "a_factor", "cagr": 0.1, "annual_return": 0.1, "volatility": 0.2, "sharpe": 1.0, "sortino": 1.0, "calmar": 1.0, "max_drawdown": -0.2, "turnover": 0.1, "coverage": 1.0, "composite_score": 0.0},
        ])
        self.assertEqual([r["factor"] for r in ranked], ["a_factor", "z_factor"])


if __name__ == "__main__":
    unittest.main()
