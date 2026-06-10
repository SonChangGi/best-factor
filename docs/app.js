(() => {
  'use strict';

  const DATA_URL = 'data/latest-results.json';
  const REPO_OWNER = 'SonChangGi';
  const REPO_NAME = 'best-factor';
  const WORKFLOW_FILE = 'update-dashboard.yml';
  const WORKFLOW_URL = `https://github.com/${REPO_OWNER}/${REPO_NAME}/actions/workflows/${WORKFLOW_FILE}`;
  const WORKFLOW_COMMAND = `gh workflow run ${WORKFLOW_FILE} --repo ${REPO_OWNER}/${REPO_NAME} --ref main`;
  const state = { payload: null, sortMetric: 'composite_score', topN: 20, filter: '' };

  const q = (selector) => document.querySelector(selector);

  document.addEventListener('DOMContentLoaded', () => {
    bindControls();
    loadDashboard();
  });

  function bindControls() {
    const sortSelect = q('#sort-select');
    const topInput = q('#topn-input');
    const factorFilter = q('#factor-filter');
    const workflowLink = q('#workflow-link');
    const workflowCommand = q('#workflow-command');
    const copyButton = q('#copy-command');

    if (sortSelect) {
      sortSelect.addEventListener('change', (event) => {
        state.sortMetric = event.target.value;
        renderAll();
      });
    }
    if (topInput) {
      topInput.addEventListener('input', (event) => {
        state.topN = Math.max(1, Math.min(50, Number(event.target.value) || 20));
        renderAll();
      });
    }
    if (factorFilter) {
      factorFilter.addEventListener('input', (event) => {
        state.filter = String(event.target.value || '').toLowerCase();
        renderAll();
      });
    }
    if (workflowLink) workflowLink.href = WORKFLOW_URL;
    if (workflowCommand) workflowCommand.textContent = WORKFLOW_COMMAND;
    if (copyButton) copyButton.addEventListener('click', copyWorkflowCommand);
  }

  async function copyWorkflowCommand() {
    const status = q('#update-status');
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('clipboard unavailable');
      await navigator.clipboard.writeText(WORKFLOW_COMMAND);
      if (status) status.textContent = '명령을 복사했습니다. 터미널에서 실행하려면 GitHub CLI 권한이 필요합니다.';
    } catch (_) {
      if (status) status.textContent = `복사할 수 없으면 직접 실행하세요: ${WORKFLOW_COMMAND}`;
    }
  }

  async function loadDashboard() {
    try {
      const response = await fetch(DATA_URL, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (payload.schema_version !== 1) {
        throw new Error(`지원하지 않는 dashboard schema_version: ${payload.schema_version ?? 'missing'}`);
      }
      state.payload = payload;
      q('#run-status').classList.remove('error');
      renderAll();
    } catch (error) {
      showFetchError(error);
    }
  }

  function showFetchError(error) {
    const status = q('#run-status');
    status.classList.add('error');
    status.textContent = `JSON 데이터를 불러오지 못했습니다. docs/ 폴더를 HTTP 서버 또는 GitHub Pages로 제공한 뒤 다시 열어주세요. (${error.message})`;
  }

  function renderAll() {
    const payload = state.payload;
    if (!payload) return;
    renderStatus(payload);
    renderSummary(payload);
    renderDiagnostics(payload);
    renderRankings(payload);
    renderHoldings(payload);
    renderMetrics(payload);
    renderMetadata(payload);
    renderCaveats(payload);
  }

  function renderStatus(payload) {
    const summary = payload.summary || {};
    q('#run-status').textContent = [
      '정적 JSON 로드 완료',
      `생성: ${fmtText(payload.generated_at)}`,
      `데이터 범위: ${fmtText(payload.data_scope)}`,
      `최고 팩터: ${fmtText(summary.best_factor)}`,
      fmtText(summary.static_data_warning),
    ].join(' · ');
  }

  function renderSummary(payload) {
    const summary = payload.summary || {};
    const cards = [
      ['Best factor', summary.best_factor, '종합 점수 기준 1위 팩터'],
      ['Composite', fmtNumber(summary.best_composite_score, 4), '여러 성과/위험 지표를 합산한 점수'],
      ['Factors', `${summary.effective_factor_count ?? '—'} / ${summary.tested_factor_count ?? '—'}`, '유효 / 테스트된 팩터 수'],
      ['Holdings', summary.holding_count, '최신 최고 팩터 편입 종목 수'],
      ['Generated', payload.generated_at, '정적 사이트 JSON 생성 시각'],
      ['Source hash', summary.source_hash || 'missing', '재현성 확인용 입력 파일 해시'],
    ];
    const root = q('#summary-cards');
    root.replaceChildren(...cards.map(([label, value, help]) => card(label, value, help)));
  }

  function renderDiagnostics(payload) {
    const summary = payload.summary || {};
    const skipped = payload.skipped_reasons || [];
    const root = q('#diagnostics-grid');
    root.replaceChildren(
      diagnosticCard('데이터 최신성', [
        ['JSON 생성', payload.generated_at],
        ['원천 fetch/run', summary.fetched_at || 'metadata missing'],
        ['Universe 기준일', summary.universe_as_of_date || 'unknown'],
        ['Data scope', payload.data_scope || 'unknown'],
        ['Data end date', summary.data_end_date || 'unknown'],
      ]),
      diagnosticCard('게이트/스킵 진단', [
        ['테스트 팩터', summary.tested_factor_count ?? 'unknown'],
        ['유효 팩터', summary.effective_factor_count ?? 'unknown'],
        ['랭킹 행', summary.ranking_count ?? 0],
        ['스킵 사유', skipped.length ? skipped.map((r) => `${r.skip_reason}: ${r.count}`).join(', ') : '없음'],
      ])
    );
  }

  function renderRankings(payload) {
    const rankings = sortedRankings(payload).filter((row) => !state.filter || String(row.factor || '').toLowerCase().includes(state.filter));
    const root = q('#ranking-list');
    if (!rankings.length) {
      root.replaceChildren(empty('표시할 팩터가 없습니다.'));
      return;
    }
    root.replaceChildren(...rankings.map((row) => {
      const article = el('article', 'rank-card');
      const head = el('div', 'rank-head');
      head.append(span(` rank #${row.rank ?? '—'}`, 'rank-badge'), strong(row.factor), span(fmtNumber(row[state.sortMetric], 4)));
      article.append(head, bar(percentForMetric(row[state.sortMetric], state.sortMetric), `정렬 지표 ${state.sortMetric}`));
      const metricRow = el('div', 'metric-row');
      metricRow.append(
        span(`CAGR ${fmtPct(row.cagr)}`),
        span(`Sharpe ${fmtNumber(row.sharpe, 2)}`),
        span(`Sortino ${fmtNumber(row.sortino, 2)}`),
        span(`Calmar ${fmtNumber(row.calmar, 2)}`),
        span(`MDD ${fmtPct(row.max_drawdown)}`)
      );
      article.append(metricRow);
      return article;
    }));
  }

  function renderHoldings(payload) {
    const holdings = (payload.latest_holdings || []).slice(0, state.topN);
    const root = q('#holdings-table');
    if (!holdings.length) {
      root.replaceChildren(empty('최신 편입 종목이 없습니다.'));
      return;
    }
    root.replaceChildren(table(
      '최신 최고 팩터 편입 종목과 표시 비중',
      ['Ticker', 'Weight', 'Score', 'Rebalance date', 'Price date used'],
      holdings.map((row) => [
        strong(row.ticker),
        weightCell(row.weight),
        fmtNumber(row.score, 4),
        fmtText(row.rebalance_date),
        fmtText(row.price_date_used),
      ])
    ));
  }

  function renderMetrics(payload) {
    const rows = sortedRankings({ rankings: payload.metrics || [] });
    const root = q('#metrics-table');
    if (!rows.length) {
      root.replaceChildren(empty('상세 지표가 없습니다.'));
      return;
    }
    root.replaceChildren(table(
      '팩터별 성과와 위험 지표. 숫자가 공식 결과입니다.',
      ['Factor', 'Composite', 'CAGR', 'Sharpe', 'Sortino', 'Calmar', 'MDD', 'Volatility', 'Coverage'],
      rows.map((row) => [
        fmtText(row.factor),
        fmtNumber(row.composite_score, 4),
        fmtPct(row.cagr),
        fmtNumber(row.sharpe, 2),
        fmtNumber(row.sortino, 2),
        fmtNumber(row.calmar, 2),
        fmtPct(row.max_drawdown),
        fmtPct(row.volatility),
        fmtPct(row.coverage),
      ])
    ));
  }

  function renderMetadata(payload) {
    const summary = payload.summary || {};
    const metadata = payload.metadata || {};
    const rows = [
      ['schema_version', payload.schema_version],
      ['generated_at', payload.generated_at],
      ['data_scope', payload.data_scope],
      ['provider', summary.provider || metadata.provider],
      ['fetched_at', summary.fetched_at || metadata.fetched_at || 'missing'],
      ['source_hash', summary.source_hash || metadata.source_hash || 'missing'],
      ['source_kind', metadata.source_kind || 'unknown'],
      ['data_end_date', summary.data_end_date || metadata.data_end_date || 'unknown'],
      ['universe_name', metadata.universe_name || 'unknown'],
      ['universe_ticker_count', metadata.universe_ticker_count || 'unknown'],
      ['timing_convention', metadata.timing_convention || 'unknown'],
      ['static_data_warning', summary.static_data_warning],
    ];
    q('#metadata-table').replaceChildren(table('실행/재현성 메타데이터', ['Key', 'Value'], rows));
  }

  function renderCaveats(payload) {
    const caveats = payload.caveats || [];
    const root = q('#caveats-list');
    root.replaceChildren(...caveats.map((item) => {
      const li = document.createElement('li');
      li.textContent = fmtText(item);
      return li;
    }));
  }

  function sortedRankings(payload) {
    return sortRows(payload.rankings || [], state.sortMetric);
  }

  function sortRows(rows, metric) {
    return [...rows].sort((a, b) => {
      const av = metricSortValue(a, metric);
      const bv = metricSortValue(b, metric);
      const delta = bv - av;
      if (delta !== 0) return delta;
      return fmtText(a.factor).localeCompare(fmtText(b.factor));
    });
  }

  function metricSortValue(row, metric) {
    const numeric = Number(row ? row[metric] : undefined);
    return Number.isFinite(numeric) ? numeric : Number.NEGATIVE_INFINITY;
  }

  function table(captionText, headers, rows) {
    const tbl = document.createElement('table');
    const caption = document.createElement('caption');
    caption.textContent = captionText;
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    headers.forEach((header) => {
      const th = document.createElement('th');
      th.textContent = header;
      headRow.append(th);
    });
    thead.append(headRow);
    const tbody = document.createElement('tbody');
    rows.forEach((row) => {
      const tr = document.createElement('tr');
      row.forEach((cell) => {
        const td = document.createElement('td');
        if (cell instanceof Node) td.append(cell);
        else td.textContent = fmtText(cell);
        tr.append(td);
      });
      tbody.append(tr);
    });
    tbl.append(caption, thead, tbody);
    return tbl;
  }

  function card(label, value, help) {
    const article = el('article', 'card');
    article.append(span(label), strong(value), small(help));
    return article;
  }

  function diagnosticCard(title, pairs) {
    const article = el('article', 'diagnostic-card');
    const heading = document.createElement('h3');
    heading.textContent = title;
    const dl = el('dl', 'kv-list');
    pairs.forEach(([key, value]) => {
      const row = document.createElement('div');
      const dt = document.createElement('dt');
      const dd = document.createElement('dd');
      dt.textContent = fmtText(key);
      dd.textContent = fmtText(value);
      row.append(dt, dd);
      dl.append(row);
    });
    article.append(heading, dl);
    return article;
  }

  function weightCell(weight) {
    const wrap = el('div', 'weight-cell');
    wrap.append(bar(Number(weight) * 100, '보유 비중', 'small'), span(fmtPct(weight)));
    return wrap;
  }

  function bar(percent, label, size) {
    const outer = el('div', size ? `bar ${size}` : 'bar');
    outer.setAttribute('aria-label', label);
    const inner = document.createElement('span');
    inner.style.width = `${clampPct(percent).toFixed(2)}%`;
    outer.append(inner);
    return outer;
  }

  function percentForMetric(value, metric) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return 0;
    if (metric === 'cagr' || metric === 'max_drawdown') return Math.abs(numeric) * 100;
    if (metric === 'composite_score') return numeric * 100;
    return numeric * 10;
  }

  function clampPct(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return 0;
    return Math.max(0, Math.min(100, numeric));
  }

  function fmtNumber(value, digits = 2) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '—';
    return numeric.toFixed(digits);
  }

  function fmtPct(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '—';
    return `${(numeric * 100).toFixed(2)}%`;
  }

  function fmtText(value) {
    if (value === null || value === undefined || value === '') return '—';
    return String(value);
  }

  function el(tag, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    return node;
  }

  function span(text, className) {
    const node = el('span', className);
    node.textContent = fmtText(text);
    return node;
  }

  function strong(text) {
    const node = document.createElement('strong');
    node.textContent = fmtText(text);
    return node;
  }

  function small(text) {
    const node = document.createElement('small');
    node.textContent = fmtText(text);
    return node;
  }

  function empty(text) {
    const node = el('p', 'empty');
    node.textContent = text;
    return node;
  }

  if (typeof globalThis !== 'undefined') {
    globalThis.__bestFactorDashboard = { sortRowsForTest: sortRows, metricSortValueForTest: metricSortValue, clampPctForTest: clampPct, workflowUrlForTest: WORKFLOW_URL, workflowCommandForTest: WORKFLOW_COMMAND };
  }
})();
