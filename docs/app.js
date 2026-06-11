(() => {
  'use strict';

  const DATA_URL = 'data/latest-results.json';
  const REPO_OWNER = 'SonChangGi';
  const REPO_NAME = 'best-factor';
  const WORKFLOW_FILE = 'update-dashboard.yml';
  const WORKFLOW_URL = `https://github.com/${REPO_OWNER}/${REPO_NAME}/actions/workflows/${WORKFLOW_FILE}`;
  const WORKFLOW_COMMAND = `gh workflow run ${WORKFLOW_FILE} --repo ${REPO_OWNER}/${REPO_NAME} --ref main`;
  const UPDATE_AUTOMATION_DEFAULT = {
    timezone: 'Asia/Seoul',
    primary_refresh_kst: '09:00',
    fallback_refresh_kst: ['10:00', '12:00', '15:00', '18:00'],
    fallback_policy: '10:00/12:00/15:00/18:00 KST scheduled checks rerun only when the deployed JSON is missing, not generated today in KST, or data_end_date is older than the latest expected US regular session.',
    manual_update_method: 'GitHub Actions workflow_dispatch'
  };
  const RANKING_DEFAULT_TOP = 20;
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const COMPARISON_PERIODS = [
    { key: 'all', label: '전체', periods: Infinity },
    { key: '1y', label: '최근 1년', periods: 12 },
    { key: '3y', label: '최근 3년', periods: 36 },
    { key: 'ytd', label: 'YTD', ytd: true },
  ];
  const COMPARISON_METRICS = [
    { key: 'cumulativeReturn', label: '누적 수익률', formatter: fmtPct },
    { key: 'cagr', label: 'CAGR', formatter: fmtPct },
    { key: 'sharpe', label: '샤프', formatter: (value) => fmtNumber(value, 2) },
    { key: 'sortino', label: '소르티노', formatter: (value) => fmtNumber(value, 2) },
    { key: 'calmar', label: '칼마', formatter: (value) => fmtNumber(value, 2) },
    { key: 'maxDrawdown', label: 'MDD', formatter: fmtPct },
    { key: 'volatility', label: '변동성', formatter: fmtPct },
  ];
  const state = { payload: null, sortMetric: 'composite_score', topN: RANKING_DEFAULT_TOP, filter: '', selectedFactors: new Set() };

  const q = (selector) => document.querySelector(selector);

  document.addEventListener('DOMContentLoaded', () => {
    bindControls();
    loadDashboard();
  });

  function bindControls() {
    const sortSelect = q('#sort-select');
    const topInput = q('#topn-input');
    const factorFilter = q('#factor-filter');
    const compareSelect = q('#factor-compare-select');
    const addCompare = q('#add-factor-compare');
    const clearCompare = q('#clear-factor-compare');
    const workflowLink = q('#workflow-link');
    const manualUpdateLink = q('#manual-update-link');
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
        state.topN = Math.max(1, Math.min(50, Number(event.target.value) || RANKING_DEFAULT_TOP));
        renderAll();
      });
    }
    if (factorFilter) {
      factorFilter.addEventListener('input', (event) => {
        state.filter = String(event.target.value || '').toLowerCase();
        renderAll();
      });
    }
    if (addCompare) addCompare.addEventListener('click', () => addSelectedFactor(compareSelect ? compareSelect.value : ''));
    if (compareSelect) {
      compareSelect.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') addSelectedFactor(compareSelect.value);
      });
    }
    if (clearCompare) {
      clearCompare.addEventListener('click', () => {
        state.selectedFactors.clear();
        renderAll();
      });
    }
    if (workflowLink) workflowLink.href = WORKFLOW_URL;
    if (manualUpdateLink) manualUpdateLink.href = WORKFLOW_URL;
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
    renderUpdatePanel(payload);
    renderEconomicAnalysis(payload);
    renderFactorExplanations(payload);
    renderDiagnostics(payload);
    renderFactorReturnChart(payload);
    renderRiskChart(payload);
    renderWeightChart(payload);
    renderCurrentOutput(payload);
    renderComparisonPanel(payload);
    renderCompareControls(payload);
    renderRankings(payload);
    renderHoldings(payload);
    renderMetrics(payload);
    renderMetadata(payload);
    renderCaveats(payload);
  }

  function renderStatus(payload) {
    const summary = payload.summary || {};
    const lines = [
      statusLine('상태', '정적 JSON 로드 완료'),
      statusLine('생성', payload.generated_at),
      statusLine('데이터 기준', summary.data_end_date || payload.data_scope),
      statusLine('자동 갱신', updateScheduleText(payload)),
      statusLine('최고 팩터', summary.best_factor),
      statusLine('주의', summary.static_data_warning)
    ];
    if (payload.data_scope === 'fixture_sample') {
      lines.push(statusLine('샘플', '체크인된 fixture 예시 데이터입니다. 최신 시장 데이터는 Actions 업데이트 후 확인하세요.'));
    }
    q('#run-status').replaceChildren(...lines);
    const generated = q('#generated-at');
    if (generated) generated.textContent = `Generated: ${fmtText(payload.generated_at)}`;
  }

  function renderSummary(payload) {
    const summary = payload.summary || {};
    const cards = [
      ['In-sample best factor', summary.best_factor, '이번 실행 후보 중 종합 점수 기준 1위 · true OOS 아님'],
      ['Composite', fmtNumber(summary.best_composite_score, 4), '성과/위험 지표를 합산한 비교 점수'],
      ['Factor zoo', `${summary.selected_factor_count ?? summary.tested_factor_count ?? '—'} / ${summary.factor_library_size ?? '—'}`, '선택/라이브러리 후보 팩터 수'],
      ['Effective', `${summary.effective_factor_count ?? '—'} / ${summary.tested_factor_count ?? '—'}`, '유효 / 테스트된 팩터 수'],
      ['Holdout rank', summary.best_factor_holdout_rank ? `#${summary.best_factor_holdout_rank}` : '—', '최근 tail 기간 보조 검증 순위'],
      ['Holdings', summary.holding_count, '최신 최고 팩터 편입 종목 수'],
      ['Data end', summary.data_end_date || payload.data_scope, '가격 데이터 기준일'],
    ];
    const nodes = cards.map(([label, value, help], index) => card(label, value, help, index === 0 ? '탐색적 · out-of-sample 아님' : ''));
    q('#summary-cards').replaceChildren(...nodes);
  }

  function renderUpdatePanel(payload) {
    const automation = automationConfig(payload);
    const scheduleList = q('#update-schedule-list');
    if (scheduleList) {
      scheduleList.replaceChildren(
        scheduleItem(`${automation.primary_refresh_kst} KST`, '기본 자동 업데이트: 새 데이터를 받아 백테스트·랭킹·Pages 배포를 실행합니다.'),
        ...automation.fallback_refresh_kst.map((time) => scheduleItem(`${time} KST`, 'fallback 최신성 확인: 공개 JSON이 없거나 stale이면 다시 실행하고, 이미 최신이면 비용 절약을 위해 스킵합니다.'))
      );
    }
    setText('#update-status', `${updateScheduleText(payload)} · 수동 업데이트는 GitHub Actions workflow_dispatch 권한이 필요합니다.`);
    const detail = `마지막 생성 ${fmtKst(payload.generated_at)} · 데이터 기준 ${fmtText((payload.summary || {}).data_end_date || (payload.metadata || {}).data_end_date)} · 판정 정책: ${automation.fallback_policy || UPDATE_AUTOMATION_DEFAULT.fallback_policy}`;
    setText('#freshness-detail', detail);
  }

  function renderEconomicAnalysis(payload) {
    const root = q('#economic-analysis-grid');
    if (!root) return;
    const summary = payload.summary || {};
    const rankings = payload.rankings || [];
    const best = rankings[0] || {};
    const metrics = metricForFactor(payload, summary.best_factor || best.factor) || best;
    const meta = factorMeta(payload, summary.best_factor || best.factor) || {};
    const holdings = payload.latest_holdings || [];
    const topWeight = Math.max(...holdings.map((row) => Number(row.weight) || 0), 0);
    const totalWeight = sumWeights(holdings);
    const holdout = holdoutSummary(summary, payload.metadata || {});
    const category = meta.category || 'unknown';

    root.replaceChildren(
      analysisCard('경제적 가설', economicNarrative(category), [
        ['팩터군', familyTitle(category)],
        ['팩터 설명', meta.description || '카탈로그 설명 없음'],
        ['신호 종류', meta.kind || 'unknown'],
      ]),
      analysisCard('성과와 위험의 균형', '단순 수익률보다 Sharpe·Sortino·Calmar·MDD를 함께 본 종합 점수 기준입니다. 높은 CAGR이라도 MDD나 변동성이 크면 랭킹에서 불리합니다.', [
        ['CAGR', fmtPct(metrics.cagr)],
        ['Sharpe / Sortino', `${fmtNumber(metrics.sharpe, 2)} / ${fmtNumber(metrics.sortino, 2)}`],
        ['Calmar / MDD', `${fmtNumber(metrics.calmar, 2)} / ${fmtPct(metrics.max_drawdown)}`],
      ]),
      analysisCard('견고성 체크', '최근 tail holdout은 완전한 untouched OOS가 아니라 후보 팩터의 최근 구간 재검산입니다. 그래도 전체 기간 1위가 최근 구간에서도 완전히 붕괴했는지 확인하는 보조 안전장치입니다.', [
        ['Holdout', holdout],
        ['Coverage', fmtPct(metrics.coverage)],
        ['Turnover', fmtPct(metrics.turnover)],
      ]),
      analysisCard('실행 전 점검', '표시 비중은 연구용 close-to-close 모델 포트폴리오입니다. 실제 운용 전 다음 세션 체결, 슬리피지, 세금, 집중도, 섹터 편중, 유동성 한도를 별도로 검증해야 합니다.', [
        ['보유 종목 수', holdings.length],
        ['최대 단일 비중', fmtPct(topWeight)],
        ['비중 합계', fmtPct(totalWeight)],
      ])
    );
  }

  function renderDiagnostics(payload) {
    const summary = payload.summary || {};
    const metadata = payload.metadata || {};
    const skipped = payload.skipped_reasons || [];
    q('#diagnostics-grid').replaceChildren(
      diagnosticCard('데이터 커버리지', [
        ['JSON 생성', payload.generated_at],
        ['원천 fetch/run', summary.fetched_at || 'metadata missing'],
        ['Universe 기준일', summary.universe_as_of_date || 'unknown'],
        ['Universe 범위', metadata.universe_scope_note || 'curated/current ticker set'],
        ['Data scope', payload.data_scope || 'unknown'],
        ['Provider', summary.provider || metadata.provider || 'unknown'],
      ]),
      diagnosticListCard('팩터/랭킹 게이트', [
        gateItem('팩터 프리셋', summary.factor_preset || metadata.factor_preset || 'unknown', 'pass'),
        gateItem('라이브러리 후보', `${summary.factor_library_size ?? metadata.factor_library_size ?? 'unknown'}개`, Number(summary.factor_library_size ?? metadata.factor_library_size) >= 300 ? 'pass' : 'warn'),
        gateItem('선택 후보', `${summary.selected_factor_count ?? metadata.selected_factor_count ?? summary.tested_factor_count ?? 'unknown'}개`, Number(summary.selected_factor_count ?? metadata.selected_factor_count ?? summary.tested_factor_count) >= 300 ? 'pass' : 'warn'),
        gateItem('테스트 팩터', `${summary.tested_factor_count ?? 'unknown'}개`, 'pass'),
        gateItem('유효 팩터', `${summary.effective_factor_count ?? 'unknown'}개`, Number(summary.effective_factor_count) > 0 ? 'pass' : 'warn'),
        gateItem('랭킹 행', `${summary.ranking_count ?? 0}개`, Number(summary.ranking_count) > 0 ? 'pass' : 'warn'),
        gateItem(
          'OHLC 조정',
          metadata.price_adjustment || '다음 run부터 adjusted-close 기준 조정값 기록',
          metadata.price_adjustment === 'open_high_low_close_scaled_to_adj_close' ? 'pass' : 'warn',
        ),
        gateItem('Holdout 보조 검증', holdoutSummary(summary, metadata), summary.best_factor_holdout_rank ? 'pass' : 'warn'),
      ]),
      diagnosticListCard('스킵/현실 제약', [
        ...(metadata.skip_resolution_note ? [gateItem('해결/보존 정책', metadata.skip_resolution_note, 'pass')] : []),
        ...(skipped.length ? skipped.map((row) => gateItem(row.skip_reason, `${row.count}개`, 'warn')) : [gateItem('스킵 사유', '없음', 'pass')]),
      ])
    );
  }

  function holdoutSummary(summary, metadata) {
    const validation = metadata.holdout_validation || {};
    const rank = summary.best_factor_holdout_rank || validation.best_factor_holdout_rank;
    const ranked = validation.holdout_ranked_factor_count;
    const cagr = summary.best_factor_holdout_cagr || validation.best_factor_holdout_cagr;
    const sharpe = summary.best_factor_holdout_sharpe || validation.best_factor_holdout_sharpe;
    if (!rank) return 'holdout 산출물 없음';
    const parts = [`rank #${rank}${ranked ? ` / ${ranked}` : ''}`];
    if (Number.isFinite(Number(cagr))) parts.push(`CAGR ${fmtPct(cagr)}`);
    if (Number.isFinite(Number(sharpe))) parts.push(`Sharpe ${fmtNumber(sharpe, 2)}`);
    return parts.join(' · ');
  }

  function renderFactorExplanations(payload) {
    const summary = payload.summary || {};
    const families = factorFamilies(payload);
    setText('#factor-scope-meta', `${summary.selected_factor_count ?? families.reduce((total, item) => total + (Number(item.count) || 0), 0)}개 후보 · ${families.length}개 팩터군`);
    const root = q('#factor-family-grid');
    if (!root) return;
    if (!families.length) {
      root.replaceChildren(empty('팩터 설명 메타데이터가 없습니다.'));
      return;
    }
    root.replaceChildren(...families.map((family) => {
      const article = el('article', 'factor-family-card');
      article.append(
        span(`${fmtText(family.category)} · ${fmtText(family.count)}개`, 'badge'),
        strong(familyTitle(family.category)),
        small(family.description || '팩터군 설명이 없습니다.')
      );
      const meta = el('div', 'factor-family-meta');
      meta.append(
        span(`종류 ${fmtText(Object.keys(family.kind_counts || {}).join(', ') || '—')}`),
        span(`PIT 재무 필요 ${fmtText(family.requires_fundamentals_count ?? 0)}개`)
      );
      const examples = el('div', 'factor-examples');
      (family.examples || []).slice(0, 6).forEach((name) => examples.append(span(name, 'factor-pill')));
      article.append(meta, examples);
      return article;
    }));
  }

  function renderFactorReturnChart(payload) {
    const rows = visibleRankings(payload).slice(0, 8);
    setText('#factor-chart-meta', `${metricLabel('cagr')} · ${rows.length}개 표시`);
    const root = q('#factor-return-chart');
    if (!rows.length) {
      root.replaceChildren(empty('표시할 팩터가 없습니다.'));
      return;
    }
    const maxAbs = Math.max(...rows.map((row) => Math.abs(Number(row.cagr) || 0)), 0.01);
    root.replaceChildren(...rows.map((row) => barRow({
      label: row.factor,
      value: fmtPct(row.cagr),
      width: (Math.abs(Number(row.cagr) || 0) / maxAbs) * 100,
      negative: Number(row.cagr) < 0,
      best: row.rank === 1,
    })));
  }

  function renderRiskChart(payload) {
    const rows = visibleRankings(payload).slice(0, 5);
    setText('#risk-chart-meta', `${rows.length}개 팩터`);
    const root = q('#risk-chart');
    if (!rows.length) {
      root.replaceChildren(empty('위험 조정 지표가 없습니다.'));
      return;
    }
    root.replaceChildren(...rows.map((row) => {
      const tile = el('article', 'metric-tile');
      const header = el('div', 'metric-tile-header');
      header.append(strong(row.factor), span(`MDD ${fmtPct(row.max_drawdown)}`));
      const metrics = el('div', 'mini-list');
      metrics.append(
        miniMetric('Sharpe', fmtNumber(row.sharpe, 2), normalizedWidth(row.sharpe, rows, 'sharpe')),
        miniMetric('Sortino', fmtNumber(row.sortino, 2), normalizedWidth(row.sortino, rows, 'sortino')),
        miniMetric('Calmar', fmtNumber(row.calmar, 2), normalizedWidth(row.calmar, rows, 'calmar'))
      );
      tile.append(header, metrics);
      return tile;
    }));
  }

  function renderWeightChart(payload) {
    const holdings = (payload.latest_holdings || []).slice(0, Math.min(state.topN, 12));
    setText('#weight-chart-meta', `${holdings.length}개 종목 · 합계 ${fmtPct(sumWeights(holdings))}`);
    const root = q('#weight-chart');
    if (!holdings.length) {
      root.replaceChildren(empty('최신 편입 종목이 없습니다.'));
      return;
    }
    const maxWeight = Math.max(...holdings.map((row) => Number(row.weight) || 0), 0.01);
    root.replaceChildren(...holdings.map((row) => barRow({
      label: row.ticker,
      value: fmtPct(row.weight),
      width: ((Number(row.weight) || 0) / maxWeight) * 100,
      best: row === holdings[0],
    })));
  }

  function renderCurrentOutput(payload) {
    const holdings = (payload.latest_holdings || []).slice(0, state.topN);
    setText('#current-output-meta', `${holdings.length}행 · 기준 ${fmtText((payload.summary || {}).data_end_date)}`);
    const tbody = q('#current-output-table tbody');
    if (!tbody) return;
    if (!holdings.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 7;
      td.textContent = '최신 편입 종목이 없습니다.';
      tr.append(td);
      tbody.replaceChildren(tr);
      return;
    }
    tbody.replaceChildren(...holdings.map((row, index) => tableRow([
      index + 1,
      strong(row.ticker),
      fmtText(row.factor),
      fmtNumber(row.score, 4),
      fmtPct(row.weight),
      fmtText(row.rebalance_date),
      fmtText(row.price_date_used),
    ])));
  }


  function renderComparisonPanel(payload) {
    const chartRoot = q('#comparison-line-chart');
    const tableRoot = q('#comparison-period-table');
    if (!chartRoot || !tableRoot) return;

    const summary = payload.summary || {};
    const bestFactor = String(summary.best_factor || ((payload.rankings || [])[0] || {}).factor || '');
    const selectedFactor = selectedComparisonFactor(payload, bestFactor);
    const bestSeries = equitySeriesFromReturns(
      factorReturnRows(payload, bestFactor),
      `최고 팩터 ${bestFactor || '—'}`,
      'best',
      bestFactor
    );
    const selectedSeries = selectedFactor && selectedFactor !== bestFactor
      ? equitySeriesFromReturns(factorReturnRows(payload, selectedFactor), `선택 팩터 ${selectedFactor}`, 'selected', selectedFactor)
      : null;
    const benchmarkSeries = equitySeriesFromReturns(
      benchmarkReturnRows(payload),
      benchmarkLabel(payload),
      'benchmark',
      (payload.metadata || {}).benchmark_tickers?.[0] || ''
    );
    const seriesList = [bestSeries, selectedSeries, benchmarkSeries].filter((series) => series && series.points.length >= 2);
    setText(
      '#comparison-chart-meta',
      `최고 ${bestFactor || '—'} · 선택 ${selectedFactor || '—'} · 벤치마크 ${benchmarkSeries.label}`
    );
    if (!seriesList.length) {
      chartRoot.replaceChildren(empty('누적 성과를 계산할 portfolio_returns 또는 benchmark_returns 데이터가 없습니다. 다음 best-factor 업데이트 run 이후 표시됩니다.'));
      tableRoot.replaceChildren(empty('기간별 성과 지표를 계산할 수 없습니다.'));
      return;
    }
    renderComparisonLineChart(chartRoot, seriesList);
    renderComparisonMetrics(payload, tableRoot, seriesList);
  }

  function selectedComparisonFactor(payload, bestFactor) {
    const selected = Array.from(state.selectedFactors).find((name) => name !== bestFactor && factorReturnRows(payload, name).length);
    if (selected) return selected;
    const ranked = payload.rankings || [];
    const nextRankedFactor = ranked.map((row) => String(row.factor || '')).find((name) => name && name !== bestFactor && factorReturnRows(payload, name).length);
    return nextRankedFactor || bestFactor || '';
  }

  function factorReturnRows(payload, factorName) {
    const name = String(factorName || '');
    return (payload.factor_period_returns || [])
      .filter((row) => String(row.factor || '') === name && Number.isFinite(Number(row.return)) && row.period_end)
      .sort((a, b) => String(a.period_end).localeCompare(String(b.period_end)));
  }

  function benchmarkReturnRows(payload) {
    const rows = (payload.benchmark_returns || [])
      .filter((row) => Number.isFinite(Number(row.return)) && row.period_end)
      .sort((a, b) => String(a.period_end).localeCompare(String(b.period_end)));
    if (!rows.length) return [];
    const firstTicker = String(rows[0].ticker || '');
    return rows.filter((row) => String(row.ticker || '') === firstTicker);
  }

  function benchmarkLabel(payload) {
    const metadata = payload.metadata || {};
    const rows = benchmarkReturnRows(payload);
    const label = metadata.benchmark_label || (rows[0] || {}).benchmark || 'Nasdaq Composite';
    const ticker = Array.isArray(metadata.benchmark_tickers) ? metadata.benchmark_tickers[0] : (rows[0] || {}).ticker;
    return ticker ? `${label} (${ticker})` : label;
  }

  function equitySeriesFromReturns(rows, label, key, sourceName) {
    if (!rows.length) return { key, label, sourceName, points: [] };
    const points = [];
    let equity = 1.0;
    let peak = 1.0;
    if (rows[0].period_start) points.push({ date: String(rows[0].period_start), equity, drawdown: 0 });
    rows.forEach((row) => {
      const periodReturn = Number(row.return);
      if (!Number.isFinite(periodReturn)) return;
      equity *= 1 + periodReturn;
      peak = Math.max(peak, equity);
      points.push({
        date: String(row.period_end),
        equity,
        drawdown: peak > 0 ? equity / peak - 1 : 0,
      });
    });
    return { key, label, sourceName, points: collapseDuplicateDatePoints(points) };
  }

  function collapseDuplicateDatePoints(points) {
    const byDate = new Map();
    points.forEach((point) => {
      if (point.date && Number.isFinite(Number(point.equity))) byDate.set(point.date, point);
    });
    return Array.from(byDate.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
  }

  function renderComparisonLineChart(root, seriesList) {
    root.replaceChildren();
    const allDates = Array.from(new Set(seriesList.flatMap((series) => series.points.map((point) => point.date)))).sort();
    const dateToIndex = new Map(allDates.map((date, index) => [date, index]));
    const returns = seriesList.flatMap((series) => series.points.map((point) => Number(point.equity) - 1)).filter(Number.isFinite);
    const ticks = niceReturnTicks(Math.min(...returns, 0), Math.max(...returns, 0));
    const minValue = Math.min(...ticks) + 1;
    const maxValue = Math.max(...ticks) + 1;
    const width = 820;
    const height = 300;
    const plot = { left: 72, right: 24, top: 22, bottom: 58 };
    const plotWidth = width - plot.left - plot.right;
    const plotHeight = height - plot.top - plot.bottom;
    const xFor = (date) => plot.left + (allDates.length <= 1 ? 0 : (dateToIndex.get(date) || 0) / (allDates.length - 1) * plotWidth);
    const yFor = (equity) => height - plot.bottom - ((equity - minValue) / Math.max(0.000001, maxValue - minValue)) * plotHeight;
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', '최고 팩터, 선택 팩터, 나스닥 지수의 누적 성과 비교');

    ticks.forEach((tick) => {
      const y = yFor(tick + 1);
      const line = document.createElementNS(SVG_NS, 'line');
      line.setAttribute('x1', String(plot.left));
      line.setAttribute('x2', String(width - plot.right));
      line.setAttribute('y1', String(y));
      line.setAttribute('y2', String(y));
      line.setAttribute('class', 'line-grid');
      svg.appendChild(line);
      appendSvgText(svg, fmtPct(tick), plot.left - 10, y + 4, 'axis-label', 'end');
    });

    appendAxisLine(svg, plot.left, plot.top, plot.left, height - plot.bottom);
    appendAxisLine(svg, plot.left, height - plot.bottom, width - plot.right, height - plot.bottom);
    chartDateTicks(allDates).forEach((tick) => {
      const x = xFor(tick.date);
      appendAxisLine(svg, x, height - plot.bottom, x, height - plot.bottom + 5);
      appendSvgText(svg, tick.label, x, height - plot.bottom + 21, 'axis-label');
    });
    appendSvgText(svg, '기간', plot.left + plotWidth / 2, height - 8, 'axis-title');
    const yTitle = appendSvgText(svg, '누적 성과', 14, plot.top + plotHeight / 2, 'axis-title');
    yTitle.setAttribute('transform', `rotate(-90 14 ${plot.top + plotHeight / 2})`);

    seriesList.forEach((series) => {
      const points = series.points.map((point) => `${xFor(point.date).toFixed(1)},${yFor(point.equity).toFixed(1)}`).join(' ');
      if (!points) return;
      const polyline = document.createElementNS(SVG_NS, 'polyline');
      polyline.setAttribute('points', points);
      polyline.setAttribute('class', `comparison-line ${series.key}`);
      svg.appendChild(polyline);
    });
    root.appendChild(svg);

    const legend = el('div', 'line-legend');
    seriesList.forEach((series) => {
      const item = document.createElement('span');
      const dot = el('span', `legend-dot ${series.key}`);
      const last = series.points[series.points.length - 1] || {};
      item.append(dot, `${series.label}: ${fmtPct((Number(last.equity) || 1) - 1)} · MDD ${fmtPct(maxDrawdownFromPoints(series.points))}`);
      legend.appendChild(item);
    });
    root.appendChild(legend);
  }

  function renderComparisonMetrics(payload, root, seriesList) {
    root.replaceChildren();
    const heading = el('div', 'performance-metrics-heading');
    const titleBox = document.createElement('div');
    const title = document.createElement('h4');
    title.textContent = '기간별 성과 지표 비교';
    const note = document.createElement('p');
    note.textContent = '각 기간별로 최고 팩터·선택 팩터·나스닥 지수의 누적 수익률, 위험조정 지표, MDD를 같은 표에서 비교합니다. 월간/주간 리밸런싱 산출물 기준이며 나스닥 지수는 편입·랭킹에 사용되지 않는 비교 기준입니다.';
    titleBox.append(title, note);
    heading.appendChild(titleBox);
    root.appendChild(heading);

    const grid = el('div', 'performance-period-grid');
    const ppy = periodsPerYear(payload);
    COMPARISON_PERIODS.forEach((period) => {
      const card = el('section', 'performance-period-card');
      const h5 = document.createElement('h5');
      h5.textContent = period.label;
      const wrap = el('div', 'performance-table-wrap');
      const tbl = document.createElement('table');
      tbl.className = 'performance-table';
      tbl.setAttribute('aria-label', `${period.label} 최고 팩터, 선택 팩터, 나스닥 지수 성과 지표 비교`);
      const thead = document.createElement('thead');
      const header = document.createElement('tr');
      appendHeaderCell(header, '지표');
      seriesList.forEach((series) => appendHeaderCell(header, shortSeriesLabel(series)));
      thead.append(header);
      const tbody = document.createElement('tbody');
      const metricsBySeries = new Map(seriesList.map((series) => [series.key, comparisonMetrics(series.points, period, ppy)]));
      COMPARISON_METRICS.forEach((metric) => {
        const tr = document.createElement('tr');
        appendMetricCell(tr, metric.label, 'metric-name');
        seriesList.forEach((series) => {
          const value = metricsBySeries.get(series.key)?.[metric.key];
          const className = ['cumulativeReturn', 'cagr', 'maxDrawdown', 'volatility'].includes(metric.key) ? signedClass(value, metric.key) : '';
          appendMetricCell(tr, metric.formatter(value), className);
        });
        tbody.append(tr);
      });
      tbl.append(thead, tbody);
      wrap.append(tbl);
      card.append(h5, wrap);
      grid.append(card);
    });
    root.appendChild(grid);
  }

  function comparisonMetrics(points, period, periodsPerYearValue) {
    const slice = periodPoints(points, period);
    const returns = returnsFromPoints(slice);
    if (slice.length < 2 || !returns.length) return {};
    const first = Number(slice[0].equity);
    const last = Number(slice[slice.length - 1].equity);
    const cumulativeReturn = first > 0 ? last / first - 1 : null;
    const years = Math.max(returns.length / periodsPerYearValue, 1 / periodsPerYearValue);
    const cagr = cumulativeReturn !== null && cumulativeReturn > -1 ? ((1 + cumulativeReturn) ** (1 / years)) - 1 : -1;
    const annualReturn = mean(returns) * periodsPerYearValue;
    const vol = stdPopulation(returns) * Math.sqrt(periodsPerYearValue);
    const downsideDev = Math.sqrt(mean(returns.map((value) => Math.min(0, value) ** 2))) * Math.sqrt(periodsPerYearValue);
    const maxDrawdown = maxDrawdownFromPoints(slice);
    return {
      cumulativeReturn,
      cagr,
      volatility: vol,
      sharpe: vol > 0 ? annualReturn / vol : null,
      sortino: downsideDev > 0 ? annualReturn / downsideDev : (annualReturn > 0 ? 999 : null),
      calmar: maxDrawdown < 0 ? cagr / Math.abs(maxDrawdown) : (cagr > 0 ? 999 : null),
      maxDrawdown,
    };
  }

  function periodPoints(points, period) {
    if (!points.length) return [];
    if (period.ytd) {
      const year = String(points[points.length - 1].date || '').slice(0, 4);
      const yearStart = `${year}-01-01`;
      const firstInYearIndex = points.findIndex((point) => String(point.date || '') >= yearStart);
      if (firstInYearIndex >= 0) {
        const startIndex = Math.max(0, firstInYearIndex - 1);
        const ytd = points.slice(startIndex);
        if (ytd.length >= 2) return ytd;
      }
      return points.slice(-Math.min(points.length, 2));
    }
    if (period.periods === Infinity) return points;
    return points.slice(-Math.min(points.length, Number(period.periods) + 1));
  }

  function returnsFromPoints(points) {
    const returns = [];
    for (let index = 1; index < points.length; index += 1) {
      const prev = Number(points[index - 1].equity);
      const curr = Number(points[index].equity);
      if (Number.isFinite(prev) && Number.isFinite(curr) && prev > 0) returns.push(curr / prev - 1);
    }
    return returns;
  }

  function maxDrawdownFromPoints(points) {
    let peak = null;
    let worst = 0.0;
    points.forEach((point) => {
      const equity = Number(point.equity);
      if (!Number.isFinite(equity)) return;
      peak = peak === null ? equity : Math.max(peak, equity);
      if (peak > 0) worst = Math.min(worst, equity / peak - 1);
    });
    return worst;
  }

  function periodsPerYear(payload) {
    return (payload.metadata || {}).rebalance_frequency === 'W' ? 52 : 12;
  }

  function shortSeriesLabel(series) {
    if (series.key === 'best') return '최고 팩터';
    if (series.key === 'selected') return '선택 팩터';
    if (series.key === 'benchmark') return '나스닥';
    return series.label;
  }

  function appendHeaderCell(row, text) {
    const th = document.createElement('th');
    th.textContent = fmtText(text);
    row.append(th);
  }

  function appendMetricCell(row, text, className) {
    const td = document.createElement('td');
    if (className) td.className = className;
    td.textContent = fmtText(text);
    row.append(td);
  }

  function appendSvgText(svg, text, x, y, className, anchor = 'middle') {
    const label = document.createElementNS(SVG_NS, 'text');
    label.textContent = fmtText(text);
    label.setAttribute('x', String(x));
    label.setAttribute('y', String(y));
    label.setAttribute('class', className);
    label.setAttribute('text-anchor', anchor);
    svg.appendChild(label);
    return label;
  }

  function appendAxisLine(svg, x1, y1, x2, y2) {
    const line = document.createElementNS(SVG_NS, 'line');
    line.setAttribute('x1', String(x1));
    line.setAttribute('y1', String(y1));
    line.setAttribute('x2', String(x2));
    line.setAttribute('y2', String(y2));
    line.setAttribute('class', 'axis-line');
    svg.appendChild(line);
  }

  function chartDateTicks(dates) {
    if (dates.length <= 6) return dates.map((date) => ({ date, label: shortDate(date) }));
    const stride = Math.ceil((dates.length - 2) / 4);
    return dates
      .map((date, index) => ({ date, index, label: shortDate(date) }))
      .filter((tick) => tick.index === 0 || tick.index === dates.length - 1 || tick.index % stride === 0)
      .slice(0, 7);
  }

  function shortDate(date) {
    const parts = String(date || '').split('-');
    if (parts.length >= 3) return `${parts[0].slice(2)}.${parts[1]}`;
    return fmtText(date);
  }

  function niceReturnTicks(minReturn, maxReturn) {
    let lower = Math.min(Number(minReturn) || 0, 0);
    let upper = Math.max(Number(maxReturn) || 0, 0);
    if (Math.abs(upper - lower) < 0.02) {
      lower -= 0.02;
      upper += 0.02;
    }
    const candidates = [0.02, 0.05, 0.1, 0.25, 0.5, 1, 2, 5];
    let step = candidates[candidates.length - 1];
    for (const candidate of candidates) {
      const count = Math.ceil(upper / candidate) - Math.floor(lower / candidate) + 1;
      if (count >= 4 && count <= 7) {
        step = candidate;
        break;
      }
    }
    const start = Math.floor(lower / step) * step;
    const end = Math.ceil(upper / step) * step;
    const ticks = [];
    for (let value = start; value <= end + step / 2; value += step) ticks.push(Number(value.toFixed(6)));
    return ticks;
  }

  function mean(values) {
    return values.length ? values.reduce((total, value) => total + value, 0) / values.length : 0;
  }

  function stdPopulation(values) {
    if (values.length < 2) return 0;
    const avg = mean(values);
    return Math.sqrt(mean(values.map((value) => (value - avg) ** 2)));
  }

  function signedClass(value, metricKey) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '';
    if (metricKey === 'maxDrawdown' || metricKey === 'volatility') return numeric < 0 ? 'negative' : '';
    return numeric >= 0 ? 'positive' : 'negative';
  }

  function renderRankings(payload) {
    const rankings = rankingsForDisplay(payload);
    const root = q('#ranking-list');
    const allVisible = visibleRankings(payload);
    const selectedExtraCount = rankings.filter((row) => state.selectedFactors.has(String(row.factor)) && !allVisible.slice(0, RANKING_DEFAULT_TOP).some((top) => top.factor === row.factor)).length;
    setText('#ranking-list-meta', `기본 Top ${RANKING_DEFAULT_TOP} · 선택 비교 ${selectedExtraCount}개 · 검색 결과 ${allVisible.length}개`);
    if (!rankings.length) {
      root.replaceChildren(empty('표시할 팩터가 없습니다.'));
      return;
    }
    root.replaceChildren(...rankings.map((row) => {
      const meta = factorMeta(payload, row.factor);
      const article = el('article', 'rank-card');
      if (state.selectedFactors.has(String(row.factor))) article.classList.add('is-selected');
      const head = el('div', 'rank-head');
      head.append(
        span(`rank #${row.rank ?? '—'}`, 'rank-badge'),
        strong(row.factor),
        span(`${metricLabel(state.sortMetric)} ${fmtMetric(row[state.sortMetric], state.sortMetric)}`)
      );
      article.append(head, bar(percentForMetric(row[state.sortMetric], state.sortMetric), `정렬 지표 ${state.sortMetric}`));
      if (meta) {
        const detail = el('div', 'rank-detail');
        detail.append(span(`${familyTitle(meta.category)} · ${fmtText(meta.kind)}`, 'badge'), small(meta.description));
        if ((meta.requires_fundamentals || []).length) {
          detail.append(span(`PIT fundamentals: ${meta.requires_fundamentals.join(', ')}`, 'badge warn-badge'));
        }
        article.append(detail);
      }
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

  function renderCompareControls(payload) {
    const select = q('#factor-compare-select');
    const chips = q('#selected-factor-chips');
    if (!select || !chips) return;
    const previous = select.value;
    const options = [option('', '비교할 팩터 선택')];
    sortedRankings(payload).forEach((row) => {
      const name = String(row.factor || '');
      if (!name || state.selectedFactors.has(name)) return;
      const meta = factorMeta(payload, name);
      options.push(option(name, `#${row.rank ?? '—'} ${name} · ${familyTitle(meta ? meta.category : '')}`));
    });
    select.replaceChildren(...options);
    select.value = options.some((node) => node.value === previous) ? previous : '';
    if (!state.selectedFactors.size) {
      chips.replaceChildren(empty('추가 비교 팩터를 선택하면 Top 20 아래에 함께 표시됩니다.'));
      return;
    }
    chips.replaceChildren(...Array.from(state.selectedFactors).sort().map((name) => {
      const chip = el('span', 'selected-chip');
      chip.append(span(name));
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = '제거';
      button.addEventListener('click', () => {
        state.selectedFactors.delete(name);
        renderAll();
      });
      chip.append(button);
      return chip;
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
      ['Ticker', 'Weight', 'Score', 'Factor', 'Rebalance date', 'Price date used'],
      holdings.map((row) => [
        strong(row.ticker),
        weightCell(row.weight),
        fmtNumber(row.score, 4),
        fmtText(row.factor),
        fmtText(row.rebalance_date),
        fmtText(row.price_date_used),
      ])
    ));
  }

  function renderMetrics(payload) {
    const rows = rankingsForDisplay({ rankings: payload.metrics || [] });
    const root = q('#metrics-table');
    if (!rows.length) {
      root.replaceChildren(empty('상세 지표가 없습니다.'));
      return;
    }
    root.replaceChildren(table(
      `Top ${RANKING_DEFAULT_TOP} 및 선택 비교 팩터의 성과와 위험 지표. 숫자가 공식 결과입니다.`,
      ['Factor', 'Composite', 'CAGR', 'Sharpe', 'Sortino', 'Calmar', 'MDD', 'Volatility', 'Turnover', 'Coverage'],
      rows.map((row) => [
        fmtText(row.factor),
        fmtNumber(row.composite_score, 4),
        fmtPct(row.cagr),
        fmtNumber(row.sharpe, 2),
        fmtNumber(row.sortino, 2),
        fmtNumber(row.calmar, 2),
        fmtPct(row.max_drawdown),
        fmtPct(row.volatility),
        fmtPct(row.turnover),
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
      ['price_adjustment', metadata.price_adjustment || 'unknown'],
      ['source_hash', summary.source_hash || metadata.source_hash || 'missing'],
      ['source_kind', metadata.source_kind || 'unknown'],
      ['data_end_date', summary.data_end_date || metadata.data_end_date || 'unknown'],
      ['universe_name', metadata.universe_name || 'unknown'],
      ['universe_ticker_count', metadata.universe_ticker_count || 'unknown'],
      ['universe_scope_note', metadata.universe_scope_note || 'unknown'],
      ['universe_is_point_in_time', metadata.universe_is_point_in_time ?? 'unknown'],
      ['market_cap_filter_basis', metadata.market_cap_filter_basis || 'unknown'],
      ['market_cap_filter_attempted', metadata.market_cap_filter_attempted ?? 'unknown'],
      ['market_cap_filter_effective', metadata.market_cap_filter_effective ?? 'unknown'],
      ['filter_fallback_reason', metadata.filter_fallback_reason || 'none'],
      ['current_screen_note', metadata.current_screen_note || 'unknown'],
      ['coverage_denominator', metadata.coverage_denominator || 'unknown'],
      ['rebalance_frequency', metadata.rebalance_frequency || 'unknown'],
      ['benchmark_tickers', metadata.benchmark_tickers || 'none'],
      ['benchmark_return_count', metadata.benchmark_return_count ?? (payload.benchmark_returns || []).length],
      ['benchmark_note', metadata.benchmark_note || 'none'],
      ['factor_preset', summary.factor_preset || metadata.factor_preset || 'unknown'],
      ['requested_factor_preset', metadata.requested_factor_preset || 'unknown'],
      ['factor_library_size', summary.factor_library_size || metadata.factor_library_size || 'unknown'],
      ['selected_factor_count', summary.selected_factor_count || metadata.selected_factor_count || 'unknown'],
      ['factor_category_counts', metadata.factor_category_counts || 'unknown'],
      ['factor_kind_counts', metadata.factor_kind_counts || 'unknown'],
      ['factor_family_count', factorFamilies(payload).length || 'unknown'],
      ['skip_resolution_note', metadata.skip_resolution_note || 'unknown'],
      ['factor_library_note', metadata.factor_library_note || 'unknown'],
      ['holdout_validation', metadata.holdout_validation || 'unknown'],
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

  function visibleRankings(payload) {
    return sortedRankings(payload).filter((row) => !state.filter || String(row.factor || '').toLowerCase().includes(state.filter));
  }

  function rankingsForDisplay(payload, selectedFactors = state.selectedFactors, limit = RANKING_DEFAULT_TOP, filter = state.filter) {
    const selected = new Set(Array.from(selectedFactors || []).map(String));
    const sorted = sortRows(payload.rankings || [], state.sortMetric);
    const base = sorted.filter((row) => !filter || String(row.factor || '').toLowerCase().includes(String(filter).toLowerCase())).slice(0, limit);
    const baseNames = new Set(base.map((row) => String(row.factor)));
    const extras = sorted.filter((row) => selected.has(String(row.factor)) && !baseNames.has(String(row.factor)));
    return [...base, ...extras];
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

  function factorCatalog(payload) {
    const metadata = payload.metadata || {};
    return Array.isArray(payload.factor_catalog) ? payload.factor_catalog : (Array.isArray(metadata.factor_catalog) ? metadata.factor_catalog : []);
  }

  function factorFamilies(payload) {
    const metadata = payload.metadata || {};
    return Array.isArray(payload.factor_family_summary) ? payload.factor_family_summary : (Array.isArray(metadata.factor_family_summary) ? metadata.factor_family_summary : []);
  }

  function factorMeta(payload, factorName) {
    const name = String(factorName || '');
    return factorCatalog(payload).find((item) => String(item.name || '') === name);
  }

  function addSelectedFactor(factorName) {
    const name = String(factorName || '').trim();
    if (!name) return;
    state.selectedFactors.add(name);
    renderAll();
  }

  function familyTitle(category) {
    const labels = {
      accumulation: '가격·거래량 확인',
      composite: '복합 팩터',
      distribution: '수익률 분포',
      growth: '성장',
      intraday: '장중/오버나잇',
      liquidity: '유동성',
      momentum: '모멘텀',
      quality: '퀄리티',
      reversal: '반전',
      risk: '위험',
      risk_adjusted_momentum: '위험조정 모멘텀',
      tail: '꼬리위험',
      trend: '추세',
      trend_quality: '추세 품질',
      value: '가치',
    };
    return labels[category] || fmtText(category);
  }

  function automationConfig(payload) {
    const automation = payload && payload.automation && typeof payload.automation === 'object' ? payload.automation : {};
    return {
      ...UPDATE_AUTOMATION_DEFAULT,
      ...automation,
      fallback_refresh_kst: Array.isArray(automation.fallback_refresh_kst) && automation.fallback_refresh_kst.length ? automation.fallback_refresh_kst : UPDATE_AUTOMATION_DEFAULT.fallback_refresh_kst,
    };
  }

  function updateScheduleText(payload) {
    const automation = automationConfig(payload || {});
    return `${automation.primary_refresh_kst} KST 자동 · ${automation.fallback_refresh_kst.join('/')} KST 실패 방지`;
  }

  function scheduleItem(time, description) {
    const li = document.createElement('li');
    li.append(strong(time), span(description));
    return li;
  }

  function fmtKst(value) {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return fmtText(value);
    return date.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', hour12: false });
  }

  function metricForFactor(payload, factorName) {
    const name = String(factorName || '');
    return (payload.metrics || []).find((row) => String(row.factor || '') === name);
  }

  function economicNarrative(category) {
    const narratives = {
      accumulation: '가격 상승이 거래대금·거래량 확인과 함께 나타나는지를 보며, 단순 가격 추세보다 수급 확인이 붙은 추세를 선호합니다.',
      composite: '여러 독립 신호를 결합해 특정 한 신호의 과최적화 위험을 낮추려는 접근입니다.',
      distribution: '수익률 분포의 비대칭성·안정성을 이용해 불리한 꼬리 또는 불안정한 수익 패턴을 피하려는 접근입니다.',
      intraday: '장중과 오버나잇 수익률 패턴 차이를 활용하지만, 실제 체결 가능성과 비용 민감도가 특히 큽니다.',
      liquidity: '거래대금·회전율이 충분하고 가격 충격 위험이 낮은 종목을 선호해 실행 가능성을 높이려는 접근입니다.',
      momentum: '투자자 과소반응, 추세 추종 수급, 리스크 프리미엄으로 설명되는 가격 지속성을 포착하려는 접근입니다.',
      reversal: '짧은 기간 과잉반응 이후 평균회귀를 기대하는 신호입니다. 시장 국면 전환에는 빠르지만 비용과 잡음에 민감합니다.',
      risk: '낮은 변동성·낮은 손실 꼬리를 선호해 위험조정 성과를 개선하려는 접근입니다.',
      risk_adjusted_momentum: '강한 추세를 선호하되 변동성이 큰 불안정한 상승을 벌점 처리해 momentum crash 위험을 줄이려는 접근입니다.',
      tail: '극단 손실과 하방 꼬리 위험을 줄여 장기 복리 훼손을 방지하려는 접근입니다.',
      trend: '여러 이동평균·추세 품질 조건으로 가격 방향성이 지속되는 종목을 선호합니다.',
      trend_quality: '수익률 경로가 매끄럽고 일관된 추세인지 평가해 급등락성 모멘텀을 구분합니다.',
      value: '가격 대비 펀더멘털 매력이 높은 종목을 선호하지만 무료 데이터의 PIT 한계 때문에 해석에 주의가 필요합니다.',
      quality: '수익성·재무 품질이 높은 기업을 선호하지만 무료 fundamental coverage와 시점 정합성 한계를 확인해야 합니다.',
      growth: '성장성이 높은 종목을 선호하지만 valuation risk와 데이터 공백에 민감합니다.',
    };
    return narratives[category] || '현재 1위 팩터의 경제적 의미는 카탈로그 메타데이터와 성과·위험 지표를 함께 확인해 해석해야 합니다.';
  }

  function analysisCard(title, body, facts) {
    const article = el('article', 'analysis-card');
    const heading = document.createElement('h3');
    heading.textContent = title;
    const paragraph = document.createElement('p');
    paragraph.textContent = body;
    const dl = el('dl', 'kv-list');
    facts.forEach(([key, value]) => {
      const dt = document.createElement('dt');
      const dd = document.createElement('dd');
      dt.textContent = fmtText(key);
      dd.textContent = fmtText(value);
      dl.append(dt, dd);
    });
    article.append(heading, paragraph, dl);
    return article;
  }

  function option(value, label) {
    const node = document.createElement('option');
    node.value = value;
    node.textContent = label;
    return node;
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
    rows.forEach((row) => tbody.append(tableRow(row)));
    tbl.append(caption, thead, tbody);
    return tbl;
  }

  function tableRow(cells) {
    const tr = document.createElement('tr');
    cells.forEach((cell) => {
      const td = document.createElement('td');
      if (cell instanceof Node) td.append(cell);
      else td.textContent = fmtText(cell);
      tr.append(td);
    });
    return tr;
  }

  function card(label, value, help, badgeText) {
    const article = el('article', 'card');
    article.append(span(label), strong(value), small(help));
    if (badgeText) article.append(span(badgeText, 'badge warn-badge card-badge'));
    return article;
  }

  function diagnosticCard(title, pairs) {
    const article = el('article', 'diagnostic-card');
    const heading = document.createElement('h3');
    heading.textContent = title;
    const dl = el('dl', 'kv-list');
    pairs.forEach(([key, value]) => {
      const dt = document.createElement('dt');
      const dd = document.createElement('dd');
      dt.textContent = fmtText(key);
      dd.textContent = fmtText(value);
      dl.append(dt, dd);
    });
    article.append(heading, dl);
    return article;
  }

  function diagnosticListCard(title, items) {
    const article = el('article', 'diagnostic-card');
    const heading = document.createElement('h3');
    const list = el('div', 'gate-list');
    heading.textContent = title;
    list.replaceChildren(...items);
    article.append(heading, list);
    return article;
  }

  function gateItem(title, detail, status) {
    const item = el('div', `gate-item ${status || 'pass'}`);
    item.append(strong(title), small(detail));
    return item;
  }

  function miniMetric(label, value, width) {
    const item = el('div', 'mini-item');
    item.append(strong(`${label} ${value}`), bar(width, label));
    return item;
  }

  function weightCell(weight) {
    const wrap = el('div', 'weight-cell');
    wrap.append(bar(Number(weight) * 100, '보유 비중'), span(fmtPct(weight)));
    return wrap;
  }

  function barRow({ label, value, width, negative, best }) {
    const row = el('div', best ? 'bar-row is-best' : 'bar-row');
    row.append(span(label, 'bar-label'), barTrack(width, negative), span(value, 'bar-value'));
    return row;
  }

  function bar(percent, label) {
    const outer = barTrack(percent, false);
    outer.setAttribute('aria-label', label);
    return outer;
  }

  function barTrack(percent, negative) {
    const track = el('div', 'bar-track');
    const fill = el('div', negative ? 'bar-fill negative' : 'bar-fill');
    fill.style.width = `${clampPct(percent).toFixed(2)}%`;
    track.append(fill);
    return track;
  }

  function statusLine(label, value) {
    const row = el('div', 'status-line');
    row.append(span(label, 'status-label'), span(value, 'status-value'));
    return row;
  }

  function normalizedWidth(value, rows, metric) {
    const max = Math.max(...rows.map((row) => Math.max(0, Number(row[metric]) || 0)), 0.01);
    return (Math.max(0, Number(value) || 0) / max) * 100;
  }

  function sumWeights(rows) {
    return rows.reduce((total, row) => total + (Number(row.weight) || 0), 0);
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

  function metricLabel(metric) {
    const labels = {
      composite_score: '종합 점수',
      sharpe: '샤프',
      sortino: '소르티노',
      calmar: '칼마',
      cagr: 'CAGR',
      max_drawdown: 'MDD',
    };
    return labels[metric] || metric;
  }

  function fmtMetric(value, metric) {
    return metric === 'cagr' || metric === 'max_drawdown' ? fmtPct(value) : fmtNumber(value, metric === 'composite_score' ? 4 : 2);
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
    if (Array.isArray(value) || typeof value === 'object') {
      try {
        return JSON.stringify(value);
      } catch (_) {
        return String(value);
      }
    }
    return String(value);
  }

  function setText(selector, value) {
    const node = q(selector);
    if (node) node.textContent = fmtText(value);
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
    const node = el('p', 'empty-state');
    node.textContent = text;
    return node;
  }

  if (typeof globalThis !== 'undefined' && globalThis.__BEST_FACTOR_TEST__) {
    globalThis.__bestFactorDashboard = {
      sortRowsForTest: sortRows,
      rankingRowsForDisplayForTest: rankingsForDisplay,
      metricSortValueForTest: metricSortValue,
      clampPctForTest: clampPct,
      workflowUrlForTest: WORKFLOW_URL,
      workflowCommandForTest: WORKFLOW_COMMAND,
      updateScheduleTextForTest: updateScheduleText,
      economicNarrativeForTest: economicNarrative,
      selectedComparisonFactorForTest: selectedComparisonFactor,
      equitySeriesFromReturnsForTest: equitySeriesFromReturns,
      comparisonMetricsForTest: comparisonMetrics,
      benchmarkLabelForTest: benchmarkLabel
    };
  }
})();
