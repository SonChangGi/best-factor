import math
import tempfile
import unittest
from pathlib import Path

from best_factor.report import _bar_width, write_html_report, write_report


class WebReportTest(unittest.TestCase):
    def test_bar_width_clamps_invalid_and_out_of_range_values(self):
        self.assertEqual(_bar_width(-25), 0.0)
        self.assertEqual(_bar_width(125), 100.0)
        self.assertEqual(_bar_width(math.nan), 0.0)
        self.assertEqual(_bar_width(math.inf), 0.0)
        self.assertEqual(_bar_width("bad"), 0.0)
        self.assertEqual(_bar_width(42.5), 42.5)

    def test_html_report_escapes_hostile_strings_and_keeps_accessible_sections(self):
        rankings = [
            {
                "rank": 1,
                "factor": '<script>alert("factor")</script>',
                "composite_score": 1.5,
                "cagr": 0.1234,
                "sharpe": 1.2,
                "sortino": 2.3,
                "calmar": 3.4,
                "max_drawdown": -0.2,
                "volatility": 0.15,
                "coverage": 1.0,
            }
        ]
        holdings = [
            {
                "ticker": '<img src=x onerror=alert("ticker")>',
                "weight": 1.2,
                "score": 9.9,
                "rebalance_date": "<2024-01-31>",
                "price_date_used": "<2024-01-31>",
            }
        ]
        skipped = {'<script>alert("skip")</script>': 2}
        metadata = {
            "provider": '<script>alert("provider")</script>',
            "provider_version": "stdlib",
            "source": 'https://example.com/text-only-source?x=<script>',
            "fetched_at": "<2026-06-10>",
            "cache_dir": "/tmp/cache",
            "universe_as_of_date": "<today>",
            "source_hash": "abc123",
            "tested_factor_count": 1,
            "effective_factor_count": 1,
            "caveats": ['Use <b>care</b> with https://example.com text URLs.'],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"
            write_html_report(path, rankings, holdings, skipped, metadata)
            html = path.read_text()

        self.assertIn("<main", html)
        self.assertIn('aria-labelledby="page-title"', html)
        self.assertIn("<caption>Factor comparison", html)
        self.assertIn("Best Factor Dashboard", html)
        self.assertIn("&lt;script&gt;alert(&quot;factor&quot;)&lt;/script&gt;", html)
        self.assertIn("&lt;img src=x onerror=alert(&quot;ticker&quot;)&gt;", html)
        self.assertIn("&lt;script&gt;alert(&quot;skip&quot;)&lt;/script&gt;", html)
        self.assertIn("&lt;script&gt;alert(&quot;provider&quot;)&lt;/script&gt;", html)
        self.assertIn("Use &lt;b&gt;care&lt;/b&gt; with https://example.com text URLs.", html)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn('style="width: 150.00%"', html)
        self.assertIn('style="width: 100.00%"', html)

    def test_html_report_has_no_external_asset_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"
            write_html_report(
                path,
                [{"rank": 1, "factor": "momentum", "composite_score": 0.5, "cagr": 0.1, "sharpe": 1, "sortino": 1, "calmar": 1, "max_drawdown": -0.1, "volatility": 0.2, "coverage": 1}],
                [{"ticker": "AAA", "weight": 1, "score": 1, "rebalance_date": "2024-01-31", "price_date_used": "2024-01-31"}],
                {},
                {"provider": "csv", "source": "https://example.com/text-only", "tested_factor_count": 1, "effective_factor_count": 1},
            )
            html = path.read_text().lower()
        for forbidden in ['src="http', "src='http", 'href="http', "href='http", "@import", "<script src=", "<link "]:
            self.assertNotIn(forbidden, html)
        self.assertNotRegex(html, r"url\(\s*['\"]?https?://")

    def test_empty_sections_render_graceful_fallbacks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.html"
            write_html_report(path, [], [], {}, {"provider": "csv", "tested_factor_count": 0, "effective_factor_count": 0})
            html = path.read_text()
        self.assertIn("No effective factor portfolio was produced.", html)
        self.assertIn("No rank-eligible factors.", html)
        self.assertIn("No metrics available.", html)
        self.assertIn("No latest holdings were available", html)
        self.assertIn("No skipped diagnostics were recorded.", html)

    def test_report_metadata_sanitizes_windows_paths(self):
        rankings = [{"rank": 1, "factor": "momentum", "composite_score": 0.5, "cagr": 0.1, "sharpe": 1, "sortino": 1, "calmar": 1, "max_drawdown": -0.1, "volatility": 0.2, "coverage": 1}]
        metadata = {
            "provider": "csv",
            "source": r"csv:C:\Users\alice\private\prices.csv",
            "cache_dir": r"C:\Users\alice\.cache\best-factor",
            "tested_factor_count": 1,
            "effective_factor_count": 1,
        }
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "report.md"
            html_path = Path(tmp) / "report.html"
            write_report(md_path, rankings, [], {}, metadata)
            write_html_report(html_path, rankings, [], {}, metadata)
            combined = md_path.read_text() + html_path.read_text()
        self.assertIn("csv:prices.csv", combined)
        self.assertIn("best-factor", combined)
        self.assertNotIn("alice", combined)
        self.assertNotIn("private", combined)
        self.assertNotIn("Users", combined)


if __name__ == "__main__":
    unittest.main()
