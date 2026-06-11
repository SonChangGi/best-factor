import importlib.util
import json
import re
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


class DocsSiteTest(unittest.TestCase):
    def test_docs_site_files_and_sections_exist(self):
        for relative in ["index.html", "styles.css", "app.js", "data/latest-results.json"]:
            self.assertTrue((DOCS / relative).exists(), relative)
        html = (DOCS / "index.html").read_text(encoding="utf-8")
        for marker in [
            "미국 주식 팩터 랭킹 대시보드",
            "run-status",
            "통합 대시보드로 돌아가기",
            "https://sonchanggi.github.io/quant-dashboard/",
            "summary-cards",
            "visual-dashboard",
            "factor-return-chart",
            "comparison-line-chart",
            "comparison-period-table",
            "최고 팩터 · 선택 팩터 · 나스닥 지수 누적 성과 비교",
            "risk-chart",
            "weight-chart",
            "current-output-table",
            "ranking-list",
            "ranking-list-meta",
            "factor-scope-title",
            "factor-family-grid",
            "factor-compare-select",
            "add-factor-compare",
            "selected-factor-chips",
            "holdings-table",
            "diagnostics-title",
            "metadata-title",
            "caveats-title",
            "update-title",
            "수동 업데이트 실행 화면 열기",
            "워크플로 상태 보기",
            "update-schedule-list",
            "09:00 KST",
            "10:00 KST",
            "12:00 KST",
            "15:00 KST",
            "18:00 KST",
            "economic-analysis-title",
            "economic-analysis-grid",
            "저장소 권한 필요",
        ]:
            self.assertIn(marker, html)

    def test_docs_assets_have_no_remote_dependencies_except_actions_link(self):
        combined = "\n".join((DOCS / name).read_text(encoding="utf-8").lower() for name in ["index.html", "styles.css", "app.js"])
        self.assertNotIn('src="http', combined)
        self.assertNotIn("src='http", combined)
        self.assertNotIn("@import", combined)
        self.assertNotRegex(combined, r"url\(\s*['\"]?https?://")
        hrefs = re.findall(r"href=[\"'](http[^\"']+)[\"']", combined)
        self.assertTrue(hrefs)
        self.assertEqual(
            set(hrefs),
            {
                "https://github.com/sonchanggi/best-factor/actions/workflows/update-dashboard.yml",
                "https://sonchanggi.github.io/quant-dashboard/",
            },
        )

    def test_docs_and_workflow_are_isolated_from_old_project(self):
        targets = [ROOT / "README.md", ROOT / "pyproject.toml", ROOT / "src", ROOT / "tests", ROOT / "docs", ROOT / ".github"]
        combined = []
        for target in targets:
            if target.is_file():
                combined.append(target.read_text(encoding="utf-8"))
            elif target.exists():
                for path in target.rglob("*"):
                    if path.is_file() and path.suffix not in {".pyc", ".pyo"}:
                        combined.append(path.read_text(encoding="utf-8"))
        haystack = "\n".join(combined)
        page_paths = re.findall(r"sonchanggi\.github\.io/([A-Za-z0-9_.-]+)", haystack)
        repo_paths = re.findall(r"github\.com/SonChangGi/([A-Za-z0-9_.-]+)", haystack)
        short_repo_paths = re.findall(r"SonChangGi/([A-Za-z0-9_.-]+)", haystack)
        self.assertTrue(page_paths)
        self.assertTrue(repo_paths)
        self.assertTrue(all(path in {"best-factor", "quant-dashboard"} for path in page_paths))
        self.assertTrue(all(path == "best-factor" for path in repo_paths))
        self.assertTrue(all(path == "best-factor" for path in short_repo_paths))

    def test_app_js_uses_safe_dom_sinks_and_fetch_failure_guidance(self):
        app = (DOCS / "app.js").read_text(encoding="utf-8")
        self.assertIn("textContent", app)
        self.assertIn("createElement", app)
        self.assertIn("HTTP 서버 또는 GitHub Pages", app)
        self.assertIn("schema_version !== 1", app)
        self.assertIn("SonChangGi", app)
        self.assertIn("best-factor", app)
        self.assertIn("JSON.stringify", app)
        self.assertIn("fixture_sample", app)
        self.assertIn("market_cap_filter_basis", app)
        self.assertIn("RANKING_DEFAULT_TOP = 20", app)
        self.assertIn("Holdout 보조 검증", app)
        self.assertIn("UPDATE_AUTOMATION_DEFAULT", app)
        self.assertIn("manual-update-link", app)
        self.assertIn("renderEconomicAnalysis", app)
        self.assertIn("economicNarrative", app)
        self.assertIn("renderComparisonPanel", app)
        self.assertIn("comparisonMetrics", app)
        self.assertIn("createElementNS", app)
        self.assertIn("기간별 성과 지표 비교", app)
        self.assertIn("rankingRowsForDisplayForTest", app)
        self.assertIn("Number.isFinite(numeric) ? numeric : Number.NEGATIVE_INFINITY", app)
        self.assertNotIn("|| -Infinity", app)
        unsafe_sinks = ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"]
        for sink in unsafe_sinks:
            self.assertNotIn(sink, app)

    @unittest.skipUnless(shutil.which("node"), "node is required for JavaScript helper smoke")
    def test_app_sorting_preserves_zero_metric_values(self):
        script = textwrap.dedent(
            f"""
            const fs = require('fs');
            const vm = require('vm');
            const code = fs.readFileSync({str(DOCS / 'app.js')!r}, 'utf8');
            const context = {{
              console,
              __BEST_FACTOR_TEST__: true,
              navigator: {{}},
              Node: function Node(){{}},
              document: {{ addEventListener(){{}}, querySelector(){{ return {{ addEventListener(){{}}, classList: {{ add(){{}}, remove(){{}} }} }}; }} }}
            }};
            context.globalThis = context;
            vm.createContext(context);
            vm.runInContext(code, context);
            const sorted = context.__bestFactorDashboard.sortRowsForTest([
              {{ factor: 'missing' }},
              {{ factor: 'minus', max_drawdown: -0.2 }},
              {{ factor: 'zero', max_drawdown: 0 }}
            ], 'max_drawdown').map((row) => row.factor).join(',');
            if (sorted !== 'zero,minus,missing') throw new Error(sorted);
            const displayed = context.__bestFactorDashboard.rankingRowsForDisplayForTest({{
              rankings: Array.from({{ length: 25 }}, (_, i) => ({{ factor: `factor_${{i + 1}}`, composite_score: 100 - i, rank: i + 1 }}))
            }}, new Set(['factor_25']), 20, '').map((row) => row.factor);
            if (displayed.length !== 21) throw new Error(`bad length ${{displayed.length}}`);
            if (displayed[19] !== 'factor_20' || displayed[20] !== 'factor_25') throw new Error(displayed.join(','));
            if (context.__bestFactorDashboard.workflowUrlForTest !== 'https://github.com/SonChangGi/best-factor/actions/workflows/update-dashboard.yml') throw new Error('bad workflow URL');
            const scheduleText = context.__bestFactorDashboard.updateScheduleTextForTest({{ automation: {{ primary_refresh_kst: '09:00' }} }});
            if (!scheduleText.includes('09:00 KST') || !scheduleText.includes('10:00/12:00/15:00/18:00 KST')) throw new Error(scheduleText);
            if (!context.__bestFactorDashboard.economicNarrativeForTest('momentum').includes('가격 지속성')) throw new Error('bad economic narrative');
            const comparisonPayload = {{
              metadata: {{ benchmark_label: 'Nasdaq Composite', benchmark_tickers: ['^IXIC'], rebalance_frequency: 'M' }},
              rankings: [{{ factor: 'best' }}, {{ factor: 'selected' }}],
              factor_period_returns: [
                {{ factor: 'best', period_start: '2025-01-31', period_end: '2025-02-28', return: 0.10 }},
                {{ factor: 'selected', period_start: '2025-01-31', period_end: '2025-02-28', return: 0.02 }},
              ],
              benchmark_returns: [
                {{ benchmark: 'Nasdaq Composite', ticker: '^IXIC', period_start: '2025-01-31', period_end: '2025-02-28', return: 0.03 }},
              ],
            }};
            if (context.__bestFactorDashboard.selectedComparisonFactorForTest(comparisonPayload, 'best') !== 'selected') throw new Error('bad selected comparison factor');
            const equity = context.__bestFactorDashboard.equitySeriesFromReturnsForTest(comparisonPayload.factor_period_returns.filter((row) => row.factor === 'best'), 'Best', 'best', 'best');
            if (equity.points.length !== 2 || Math.abs(equity.points[1].equity - 1.10) > 0.000001) throw new Error('bad equity series');
            const metrics = context.__bestFactorDashboard.comparisonMetricsForTest(equity.points, {{ key: 'all', label: '전체', periods: Infinity }}, 12);
            if (Math.abs(metrics.cumulativeReturn - 0.10) > 0.000001) throw new Error('bad comparison metrics');
            const ytdMetrics = context.__bestFactorDashboard.comparisonMetricsForTest([
              {{ date: '2024-12-31', equity: 1.00 }},
              {{ date: '2025-01-31', equity: 1.02 }},
              {{ date: '2025-02-28', equity: 1.05 }}
            ], {{ key: 'ytd', label: 'YTD', ytd: true }}, 12);
            if (Math.abs(ytdMetrics.cumulativeReturn - 0.05) > 0.000001) throw new Error(`bad YTD baseline ${{ytdMetrics.cumulativeReturn}}`);
            const reboundMetrics = context.__bestFactorDashboard.comparisonMetricsForTest([
              {{ date: '2024-12-31', equity: 0.80 }},
              {{ date: '2025-01-31', equity: 0.90 }}
            ], {{ key: 'all', label: '전체', periods: Infinity }}, 12);
            if (Math.abs(reboundMetrics.maxDrawdown) > 0.000001) throw new Error(`bad rebased MDD ${{reboundMetrics.maxDrawdown}}`);
            if (context.__bestFactorDashboard.benchmarkLabelForTest(comparisonPayload) !== 'Nasdaq Composite (^IXIC)') throw new Error('bad benchmark label');
            const proxyPayload = {{
              metadata: {{ benchmark_label: 'Nasdaq Composite', benchmark_tickers: ['^IXIC', 'ONEQ'], rebalance_frequency: 'M' }},
              benchmark_returns: [
                {{ benchmark: 'Nasdaq Composite ETF proxy', ticker: 'ONEQ', period_start: '2025-01-31', period_end: '2025-02-28', return: 0.03 }},
              ],
            }};
            if (context.__bestFactorDashboard.benchmarkLabelForTest(proxyPayload) !== 'Nasdaq Composite ETF proxy (ONEQ)') throw new Error('bad proxy benchmark label');
            """
        )
        completed = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_sample_json_matches_schema_and_freshness_contract(self):
        payload = json.loads((DOCS / "data" / "latest-results.json").read_text(encoding="utf-8"))
        for key in ["schema_version", "generated_at", "data_scope", "summary", "rankings", "metrics", "latest_holdings", "factor_period_returns", "benchmark_returns", "skipped_reasons", "holdout_rankings", "holdout_metrics", "factor_catalog", "factor_family_summary", "metadata", "automation", "caveats"]:
            self.assertIn(key, payload)
        self.assertEqual(payload["schema_version"], 1)
        self.assertRegex(payload["generated_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertIn(payload["data_scope"], {"fixture_sample", "live_yfinance_curated_us_large_liquid_actions"})
        self.assertIn("static_data_warning", payload["summary"])
        self.assertNotIn("run_config", payload["metadata"])
        self.assertNotIn("cache_dir", payload["metadata"])
        self.assertNotIn("prices_file", json.dumps(payload["metadata"]))
        self.assertTrue(payload["rankings"])
        self.assertTrue(payload["latest_holdings"])
        self.assertGreaterEqual(payload["summary"].get("factor_library_size", 0), 300)
        self.assertGreaterEqual(payload["summary"].get("selected_factor_count", 0), 300)
        self.assertTrue(payload["factor_catalog"])
        self.assertTrue(payload["factor_family_summary"])
        self.assertTrue(any(row.get("category") == "intraday" for row in payload["factor_family_summary"]))
        self.assertIn("factor_category_counts", payload["metadata"])
        self.assertIn("factor_kind_counts", payload["metadata"])
        self.assertIn("factor_family_summary", payload["metadata"])
        self.assertIn("skip_resolution_note", payload["metadata"])
        if payload["metadata"].get("holdout_validation"):
            self.assertIn("best_factor_holdout_rank", payload["metadata"]["holdout_validation"])
        self.assertIn("market_cap_filter_basis", payload["metadata"])
        self.assertIn("market_cap_filter_attempted", payload["metadata"])
        self.assertIn("market_cap_filter_effective", payload["metadata"])
        self.assertIn("filter_fallback_reason", payload["metadata"])
        self.assertIn("universe_scope_note", payload["metadata"])
        self.assertIn("coverage_denominator", payload["metadata"])
        self.assertIn("rebalance_frequency", payload["metadata"])
        self.assertIn("benchmark_tickers", payload["metadata"])
        self.assertIn("benchmark_return_count", payload["metadata"])
        self.assertIn("benchmark_note", payload["metadata"])
        self.assertIn("current_screen_note", payload["metadata"])
        self.assertFalse(payload["metadata"].get("universe_is_point_in_time"))
        self.assertIn("same-close", payload["metadata"].get("timing_convention", ""))
        self.assertIn("multiple-testing", " ".join(payload["caveats"]))
        self.assertEqual(payload["automation"].get("timezone"), "Asia/Seoul")
        self.assertEqual(payload["automation"].get("primary_refresh_kst"), "09:00")
        self.assertIn("10:00", payload["automation"].get("fallback_refresh_kst", []))
        self.assertIn("12:00", payload["automation"].get("fallback_refresh_kst", []))
        self.assertIn("15:00", payload["automation"].get("fallback_refresh_kst", []))
        self.assertIn("18:00", payload["automation"].get("fallback_refresh_kst", []))

    def test_hostile_json_would_not_be_injected_into_static_shell(self):
        html = (DOCS / "index.html").read_text(encoding="utf-8")
        app = (DOCS / "app.js").read_text(encoding="utf-8")
        hostile_values = ['<script>alert("x")</script>', '<img src=x onerror=alert("x")>', 'javascript:alert(1)']
        for value in hostile_values:
            self.assertNotIn(value, html)
        self.assertIn("textContent = fmtText", app)
        self.assertNotIn("innerHTML", app)

    def test_update_workflow_uses_custom_pages_deploy_without_self_push(self):
        workflow = (ROOT / ".github" / "workflows" / "update-dashboard.yml").read_text(encoding="utf-8")
        for marker in [
            "workflow_dispatch",
            "cron: \"0 0 * * *\"",
            "cron: \"0 1 * * *\"",
            "cron: \"0 3 * * *\"",
            "cron: \"0 6 * * *\"",
            "cron: \"0 9 * * *\"",
            "Check KST dashboard freshness gate",
            "check_dashboard_freshness.py",
            "steps.freshness.outputs.should_update == 'true'",
            "contents: read",
            "pages: write",
            "id-token: write",
            "actions/configure-pages@v6",
            "actions/upload-pages-artifact@v5",
            "actions/deploy-pages@v5",
            "actions/upload-artifact@v7",
            "NODE_OPTIONS: --no-deprecation",
            "github.repository == 'SonChangGi/best-factor'",
            "github.ref == 'refs/heads/main'",
            "live_yfinance_curated_us_large_liquid_actions",
            "--market-cap-filter-attempted",
            "MARKET_CAP_ELIGIBLE_COUNT",
            "market_cap_metadata_insufficient_preflight",
            "--top-n \"${TOP_N}\"",
            "--benchmark-tickers '^IXIC' ONEQ QQQ",
        ]:
            self.assertIn(marker, workflow)
        self.assertNotIn("30 22 * * 1-5", workflow)
        self.assertNotIn("if ! python -m best_factor.cli run", workflow)
        self.assertNotIn("git commit", workflow)
        self.assertNotIn("git push", workflow)

    def test_dashboard_universe_is_committed_individual_stock_list(self):
        ticker_file = ROOT / ".github" / "best-factor-dashboard-tickers.txt"
        self.assertTrue(ticker_file.exists())
        tickers = [line.split("#", 1)[0].strip() for line in ticker_file.read_text(encoding="utf-8").splitlines()]
        tickers = [ticker for ticker in tickers if ticker]
        self.assertGreaterEqual(len(tickers), 40)
        self.assertEqual(len(tickers), len(set(tickers)))
        for forbidden in {"SPY", "QQQ", "IWM", "DIA", "VTI", "VOO"}:
            self.assertNotIn(forbidden, tickers)

    def test_live_universe_helper_parses_ticker_file_without_network(self):
        script = ROOT / ".github" / "scripts" / "build_live_universe.py"
        spec = importlib.util.spec_from_file_location("build_live_universe", script)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        tickers = module.read_tickers(ROOT / ".github" / "best-factor-dashboard-tickers.txt")
        self.assertIn("AAPL", tickers)
        self.assertNotIn("SPY", tickers)


if __name__ == "__main__":
    unittest.main()
