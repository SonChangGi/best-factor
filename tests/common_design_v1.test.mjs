import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const html = readFileSync(new URL('../docs/index.html', import.meta.url), 'utf8');
const app = readFileSync(new URL('../docs/app.js', import.meta.url), 'utf8');

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

test('result-first shell keeps the primary chart ahead of secondary detail', () => {
  const summary = html.indexOf('id="summary-cards"');
  const chart = html.indexOf('id="comparison-line-chart"');
  const diagnostics = html.indexOf('id="diagnostics-title"');
  assert.ok(summary > 0);
  assert.ok(chart > summary);
  assert.ok(diagnostics > chart);
  assert.match(html, /class="skip-link"/);
  assert.match(html, /id="comparison-series-controls"/);
  assert.match(html, /id="comparison-date-input"/);
  assert.match(html, /id="comparison-value-grid"/);
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
