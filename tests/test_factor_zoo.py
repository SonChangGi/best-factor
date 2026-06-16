import datetime as dt
import math
import statistics
import time
import unittest

from best_factor.factors import (
    DEFAULT_FACTORS,
    _population_stdev,
    build_score_index,
    compute_factor_scores,
    factor_catalog,
    factor_category_counts,
    factor_family_summary,
    factor_kind_counts,
    factor_names_for_preset,
    rows_for_factor_date,
)
from best_factor.portfolio import run_backtests


REPRESENTATIVE_FACTORS = [
    "mom_252d_skip_21d",
    "vol_downside_63d",
    "ramom_126d_skip_21d_vol_63d",
    "dvol_avg_63d",
    "amihud_illiq_63d",
    "ma_gap_50d",
    "ma_cross_20d_100d",
    "range_pos_63d",
    "drawdown_high_126d",
    "accel_21d_126d_skip_0d",
    "skew_63d",
    "kurtosis_low_63d",
    "tail_loss_63d",
    "trend_efficiency_63d",
    "return_consistency_63d",
    "dvol_shock_21d_63d",
    "price_volume_corr_63d",
    "breakout_63d",
    "range_contraction_21d_63d",
    "overnight_return_21d",
    "intraday_return_21d",
]


class FactorZooTest(unittest.TestCase):
    def test_default_factor_library_is_zoo_scale_and_unique(self):
        names = [factor.name for factor in DEFAULT_FACTORS]
        self.assertGreaterEqual(len(names), 300)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(factor_names_for_preset("core")), 9)
        self.assertEqual(len(factor_names_for_preset("zoo")), len(names))
        counts = factor_category_counts()
        for category in ["momentum", "risk", "risk_adjusted_momentum", "liquidity", "trend", "trend_quality", "distribution", "tail", "accumulation", "intraday", "composite"]:
            self.assertGreater(counts.get(category, 0), 0, category)
        kinds = factor_kind_counts()
        for kind in ["return_skew", "tail_loss", "trend_efficiency", "price_volume_corr", "overnight_return", "intraday_return"]:
            self.assertGreater(kinds.get(kind, 0), 0, kind)
        families = factor_family_summary()
        self.assertGreaterEqual(len(families), 12)
        self.assertTrue(any(family["category"] == "intraday" for family in families))
        catalog = factor_catalog(["skew_63d", "overnight_return_21d"])
        self.assertEqual([row["name"] for row in catalog], ["skew_63d", "overnight_return_21d"])
        self.assertIn("category_description", catalog[0])

    def test_fast_population_stdev_matches_standard_library(self):
        values = [0.01, -0.03, 0.04, 0.0, 0.02]
        self.assertAlmostEqual(_population_stdev(values), statistics.pstdev(values), places=15)
        self.assertEqual(_population_stdev([]), 0.0)

    def test_representative_generated_factors_score_with_sufficient_history(self):
        prices = _factor_prices(tickers=("AAA", "BBB"), days=800)
        signal_date = max(row["date"] for row in prices)
        scores = compute_factor_scores(prices, [signal_date], {}, REPRESENTATIVE_FACTORS, REPRESENTATIVE_FACTORS)
        self.assertEqual(len(scores), len(REPRESENTATIVE_FACTORS) * 2)
        by_factor = {name: [row for row in scores if row["factor"] == name] for name in REPRESENTATIVE_FACTORS}
        for name, rows in by_factor.items():
            with self.subTest(factor=name):
                self.assertEqual(len(rows), 2)
                self.assertTrue(any(row["eligible"] for row in rows), rows)
                self.assertTrue(all(math.isfinite(float(row["score"])) for row in rows if row["eligible"]), rows)

    def test_score_index_keeps_factor_date_lookup_fast_at_zoo_scale(self):
        tickers = [f"T{i:03d}" for i in range(50)]
        factors = [f"synthetic_{i:03d}" for i in range(200)]
        dates = [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(61)]
        prices = [
            {"ticker": ticker, "date": date, "adj_close": 100.0 + i + j * 0.01, "volume": 1_000_000}
            for j, ticker in enumerate(tickers)
            for i, date in enumerate(dates)
        ]
        universe = [{"ticker": ticker, "market_cap": 1e10, "active": True, "asset_type": "stock"} for ticker in tickers]
        signal_dates = dates[:-1]
        scores = [
            {
                "factor": factor,
                "ticker": ticker,
                "signal_date": signal_date,
                "score": (factor_idx * 0.001) + ticker_idx,
                "eligible": True,
                "skip_reason": "",
            }
            for factor_idx, factor in enumerate(factors)
            for signal_date in signal_dates
            for ticker_idx, ticker in enumerate(tickers)
        ]
        index = build_score_index(scores)
        self.assertEqual(len(rows_for_factor_date(index, factors[0], signal_dates[0])), 50)

        start = time.perf_counter()
        result = run_backtests(prices, universe, scores, dates, top_n=10)
        duration = time.perf_counter() - start
        self.assertEqual(len(result["returns"]), len(factors) * (len(dates) - 1))
        self.assertLess(duration, 10.0, f"zoo-scale backtest lookup is too slow: {duration:.2f}s")


def _factor_prices(tickers=("AAA",), days=800):
    rows = []
    start = dt.date(2021, 1, 1)
    for ticker_idx, ticker in enumerate(tickers):
        base = 80.0 + ticker_idx * 25.0
        trend = 0.07 + ticker_idx * 0.03
        volume_base = 1_000_000 + ticker_idx * 300_000
        for i in range(days):
            date = start + dt.timedelta(days=i)
            seasonal = ((i % 17) - 8) * (0.08 + ticker_idx * 0.03)
            close = base + trend * i + seasonal
            rows.append(
                {
                    "ticker": ticker,
                    "date": date,
                    "open": close * 0.995,
                    "high": close * 1.012,
                    "low": close * 0.988,
                    "close": close,
                    "adj_close": close,
                    "volume": volume_base + (i % 13) * 10_000,
                }
            )
    return rows


if __name__ == "__main__":
    unittest.main()
