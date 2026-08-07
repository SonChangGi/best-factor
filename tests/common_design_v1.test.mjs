import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const html = readFileSync(new URL('../docs/index.html', import.meta.url), 'utf8');
const app = readFileSync(new URL('../docs/app.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../docs/styles.css', import.meta.url), 'utf8');

function dashboardHelpers() {
  const context = {
    console,
    __BEST_FACTOR_TEST__: true,
    navigator: {},
    Node: function Node() {},
    document: {
      addEventListener() {},
      querySelector() {
        return {
          addEventListener() {},
          classList: { add() {}, remove() {} },
        };
      },
    },
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(app, context);
  return context.__bestFactorDashboard;
}

test('web design v2 keeps results and the primary chart ahead of rerun inputs and detail', () => {
  const summary = html.indexOf('id="summary-cards"');
  const appliedConfig = html.indexOf('id="applied-config-summary"');
  const controls = html.indexOf('class="controls controls-enhanced viz-controls"');
  const readout = html.indexOf('id="comparison-value-grid"');
  const chart = html.indexOf('id="comparison-line-chart"');
  const analysisForm = html.indexOf('id="analysis-settings-form"');
  const secondaryResults = html.indexOf('id="secondary-results"');
  const diagnostics = html.indexOf('id="diagnostics-title"');
  assert.ok(summary > 0);
  assert.ok(appliedConfig > summary);
  assert.ok(controls > appliedConfig);
  assert.ok(readout > controls);
  assert.ok(chart > readout);
  assert.ok(analysisForm > chart);
  assert.ok(secondaryResults > analysisForm);
  assert.ok(diagnostics > secondaryResults);
  assert.match(html, /class="controls controls-enhanced viz-controls"[^>]*\sopen>/);
  assert.match(html, /<span class="eyebrow">Display only<\/span>/);
  assert.doesNotMatch(html, /class="analysis-settings-disclosure analysis-rerun-disclosure"[^>]*\sopen>/);
  assert.match(html, /class="skip-link"/);
  assert.match(html, /id="comparison-series-controls"/);
  assert.match(html, /id="comparison-date-input"/);
  assert.match(html, /id="comparison-date-observation"/);
  assert.match(html, /id="comparison-value-grid"/);
  assert.match(css, /\.controls-grid\s*\{[\s\S]*?align-items:\s*start;/);
  assert.match(css, /\.controls-grid input,\s*\.controls-grid select\s*\{[\s\S]*?height:\s*42px;[\s\S]*?min-height:\s*42px;/);
  assert.match(css, /\.controls-grid \.compare-actions button\s*\{[\s\S]*?height:\s*42px;[\s\S]*?min-height:\s*42px;/);
  assert.doesNotMatch(html, /Python 분석 결과는 다시 계산하지 않습니다/);
  assert.doesNotMatch(html, /기본 화면은 공식 1위 팩터를 유지/);
});

test('analysis rerun form exposes canonical inputs while display controls remain presentation-only', () => {
  const analysisForm = html.match(/<form id="analysis-settings-form"[\s\S]*?<\/form>/)?.[0] || '';
  const inputNames = [...analysisForm.matchAll(/name="([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(inputNames, [
    'period',
    'rebalance',
    'factor_preset',
    'factor_allowlist',
    'top_n',
    'weighting',
    'min_market_cap',
    'min_dollar_volume',
    'eligibility_adv_window',
    'transaction_cost_bps',
    'transaction_cost_model',
  ]);
  assert.match(html, /id="analysis-period"[\s\S]*?<option value="2y">2년<\/option>[\s\S]*?<option value="5y">5년<\/option>[\s\S]*?<option value="10y">10년<\/option>/);
  assert.doesNotMatch(html, /<option value="(?:1y|3y|max)">/);
  assert.match(html, /분석 편입 상한[\s\S]*?id="analysis-top-n"/);
  assert.match(html, /보유 종목 표시 행[\s\S]*?id="topn-input"/);
  assert.match(app, /저장된 결과 중 최대 \$\{available\}행 · 화면에만 적용/);
  assert.match(html, /id="analysis-workflow-command"/);
  assert.match(html, /id="copy-analysis-command"/);
  assert.match(html, /id="reset-analysis-settings"/);
  assert.match(html, /id="analysis-workflow-link"/);
  assert.match(html, /id="hero-holdings-link"/);
  assert.match(html, /id="applied-config-title"/);
  assert.match(html, /id="applied-config-status"/);
  assert.match(app, /loadAnalysisConfigSidecar\(payload\)/);
});

test('canonical navigation has the exact 10-project order and one current page', () => {
  const nav = html.match(/<div class="site-nav-links"[^>]*>([\s\S]*?)<\/div>/)?.[1] || '';
  const links = [...nav.matchAll(/<a(?: class="[^"]*")? href="([^"]+)"(?: aria-current="page")?>([\s\S]*?)<\/a>/g)]
    .map((match) => ({
      href: match[1],
      label: match[2].replace(/&amp;/g, '&').trim(),
    }));
  assert.deepEqual(links, [
    { label: 'Hub', href: 'https://sonchanggi.github.io/quant-dashboard/' },
    { label: 'Fear & Greed', href: 'https://sonchanggi.github.io/fearNgreed/' },
    { label: 'Momentum', href: 'https://sonchanggi.github.io/momentum-factor-lab/' },
    { label: 'DRAM', href: 'https://sonchanggi.github.io/dram-price/' },
    { label: 'Best Factor', href: 'https://sonchanggi.github.io/best-factor/' },
    { label: 'ETF', href: 'https://sonchanggi.github.io/etf-tracking/' },
    { label: 'SOX', href: 'https://sonchanggi.github.io/sox/' },
    { label: 'Risk Score', href: 'https://sonchanggi.github.io/quant-dashboard/risk-score/' },
    { label: 'Port', href: 'https://sonchanggi.github.io/port/' },
    { label: 'Valuation', href: 'https://sonchanggi.github.io/valuation/' },
  ]);
  assert.equal((nav.match(/aria-current="page"/g) || []).length, 1);
});

test('compact typography and non-overlapping chart readout are explicit contracts', () => {
  assert.match(css, /body\s*\{[\s\S]*?font-size:\s*15px;[\s\S]*?line-height:\s*1\.55;/);
  assert.match(css, /\.chart-active-readout\s*\{[\s\S]*?display:\s*none\s*!important;/);
  assert.match(css, /@media \(max-width:\s*1180px\)[\s\S]*?\.page-jump-nav\s*\{[\s\S]*?display:\s*none;/);
  assert.doesNotMatch(css, /content:\s*"(?:안에서 스크롤|표 안에서 스크롤|가로로 드래그)"/);
  assert.match(app, /'etf-tracking-theme'/);
  assert.match(app, /'sox-theme'/);
  assert.match(app, /revealCurrentNavItem/);
});

test('chart date navigation snaps to observations without changing analysis data', () => {
  const helpers = dashboardHelpers();
  const dates = ['2025-01-31', '2025-02-28', '2025-03-31'];
  assert.equal(helpers.nearestChartDateForTest(dates, null), '2025-03-31');
  assert.equal(helpers.nearestChartDateForTest(dates, '2025-02-28'), '2025-02-28');
  assert.equal(helpers.nearestChartDateForTest(dates, '2025-02-10'), '2025-01-31');
});

test('chart readout uses the exact or latest prior observation', () => {
  const helpers = dashboardHelpers();
  const points = [
    { date: '2025-01-31', equity: 1.0 },
    { date: '2025-02-28', equity: 1.1 },
  ];
  assert.deepEqual(
    { ...helpers.chartPointAtDateForTest(points, '2025-02-28') },
    { date: '2025-02-28', equity: 1.1 },
  );
  assert.deepEqual(
    { ...helpers.chartPointAtDateForTest(points, '2025-02-15') },
    { date: '2025-01-31', equity: 1.0 },
  );
});

test('analysis command uses canonical safe fields and explicit preset reset sentinel', () => {
  const helpers = dashboardHelpers();
  const bootstrap = helpers.analysisConfigFromPayloadForTest({
    summary: { holding_count: 7 },
    latest_holdings: Array.from({ length: 7 }, () => ({})),
    metadata: {},
  });
  assert.equal(bootstrap.top_n, 20);
  assert.equal(bootstrap.period, '5y');
  const command = helpers.buildAnalysisWorkflowCommandForTest(bootstrap);
  assert.equal((command.match(/--raw-field/g) || []).length, 11);
  assert.match(command, /--raw-field 'period=5y'/);
  assert.match(command, /--raw-field 'top_n=20'/);
  assert.match(command, /--raw-field 'factor_allowlist=__preset__'/);
  assert.doesNotMatch(command, /token|authorization|curl/i);

  const explicit = helpers.normalizeAnalysisConfigForTest({
    ...bootstrap,
    factor_allowlist: 'momentum_6m, momentum_6m,low_volatility',
  });
  assert.equal(explicit.factor_allowlist, 'momentum_6m,low_volatility');
  assert.match(
    helpers.buildAnalysisWorkflowCommandForTest(explicit),
    /--raw-field 'factor_allowlist=momentum_6m,low_volatility'/,
  );
  assert.throws(
    () => helpers.normalizeAnalysisConfigForTest({ ...bootstrap, period: '3y' }),
    /period/,
  );
  assert.throws(
    () => helpers.normalizeAnalysisConfigForTest({ ...bootstrap, factor_allowlist: "momentum_6m';rm" }),
    /직접 선택 팩터/,
  );
});

test('applied settings require an exact result binding and market-cap zero stays disabled', () => {
  const helpers = dashboardHelpers();
  const payload = {
    generated_at: '2026-07-23T23:16:07Z',
    summary: {
      source_hash: 'a54e4adee3d58bc3',
      data_end_date: '2026-07-23',
    },
    metadata: {},
  };
  assert.deepEqual(
    { ...helpers.validateResultBindingForTest({
      generated_at: '2026-07-23T23:16:07Z',
      source_hash: 'a54e4adee3d58bc3',
      data_end_date: '2026-07-23',
    }, payload) },
    { valid: true, status: 'bound' },
  );
  assert.deepEqual(
    { ...helpers.validateResultBindingForTest(null, payload) },
    { valid: false, status: 'missing' },
  );
  assert.deepEqual(
    { ...helpers.validateResultBindingForTest({
      generated_at: '2026-07-23T23:16:07Z',
      source_hash: 'different',
      data_end_date: '2026-07-23',
    }, payload) },
    { valid: false, status: 'mismatch' },
  );
  assert.deepEqual(
    { ...helpers.validateResultBindingForTest({
      generated_at: '2026-07-23T23:16:07Z',
      source_hash: 'a54e4adee3d58bc3',
      data_end_date: '2026-07-23',
      extra: 'not allowed',
    }, payload) },
    { valid: false, status: 'invalid' },
  );
  assert.equal(
    helpers.marketCapDisplayForTest({ min_market_cap: 0 }, { market_cap_filter_effective: false }),
    '없음',
  );
  assert.match(
    helpers.marketCapDisplayForTest({ min_market_cap: 10000000000 }, { market_cap_filter_effective: false }),
    /요청 \$10B · 이번 실행 미적용/,
  );
  assert.equal(helpers.bindingStatusTextForTest('mismatch'), '설정 연결 확인 필요 · 결과 불일치');
  assert.equal(helpers.bindingStatusTextForTest('missing'), '설정 연결 확인 필요 · 설정 없음');
  assert.equal(helpers.bindingStatusTextForTest('invalid'), '설정 연결 확인 필요 · 파일 오류');
});
