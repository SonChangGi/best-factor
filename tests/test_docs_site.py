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
            "summary-cards",
            "visual-dashboard",
            "factor-return-chart",
            "risk-chart",
            "weight-chart",
            "current-output-table",
            "ranking-list",
            "holdings-table",
            "diagnostics-title",
            "metadata-title",
            "caveats-title",
            "update-title",
            "GitHub Actions 업데이트 워크플로 열기",
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
        self.assertEqual(hrefs, ["https://github.com/sonchanggi/best-factor/actions/workflows/update-dashboard.yml"])

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
        self.assertTrue(all(path == "best-factor" for path in page_paths))
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
            if (context.__bestFactorDashboard.workflowUrlForTest !== 'https://github.com/SonChangGi/best-factor/actions/workflows/update-dashboard.yml') throw new Error('bad workflow URL');
            """
        )
        completed = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_sample_json_matches_schema_and_freshness_contract(self):
        payload = json.loads((DOCS / "data" / "latest-results.json").read_text(encoding="utf-8"))
        for key in ["schema_version", "generated_at", "data_scope", "summary", "rankings", "metrics", "latest_holdings", "skipped_reasons", "metadata", "caveats"]:
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
        self.assertGreaterEqual(payload["summary"].get("factor_library_size", 0), 200)
        self.assertGreaterEqual(payload["summary"].get("selected_factor_count", 0), 200)
        self.assertIn("factor_category_counts", payload["metadata"])
        self.assertIn("market_cap_filter_basis", payload["metadata"])
        self.assertIn("current_screen_note", payload["metadata"])
        self.assertFalse(payload["metadata"].get("universe_is_point_in_time"))
        self.assertIn("same-close", payload["metadata"].get("timing_convention", ""))
        self.assertIn("multiple-testing", " ".join(payload["caveats"]))

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
            "contents: read",
            "pages: write",
            "id-token: write",
            "actions/configure-pages@v6",
            "actions/upload-pages-artifact@v5",
            "actions/deploy-pages@v5",
            "github.repository == 'SonChangGi/best-factor'",
            "github.ref == 'refs/heads/main'",
            "live_yfinance_curated_us_large_liquid_actions",
        ]:
            self.assertIn(marker, workflow)
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
