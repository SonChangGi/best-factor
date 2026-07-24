(() => {
  'use strict';

  const DATA_URL = 'data/latest-results.json';
  const ANALYSIS_CONFIG_URL = 'data/dashboard-config.json';
  const REPO_OWNER = 'SonChangGi';
  const REPO_NAME = 'best-factor';
  const WORKFLOW_FILE = 'update-dashboard.yml';
  const WORKFLOW_URL = `https://github.com/${REPO_OWNER}/${REPO_NAME}/actions/workflows/${WORKFLOW_FILE}`;
  const WORKFLOW_COMMAND = `gh workflow run ${WORKFLOW_FILE} --repo ${REPO_OWNER}/${REPO_NAME} --ref main`;
  const ANALYSIS_INPUTS = [
    { key: 'period', selector: '#analysis-period', type: 'enum', allowed: ['2y', '5y', '10y'], fallback: '5y' },
    { key: 'rebalance', selector: '#analysis-rebalance', type: 'enum', allowed: ['M', 'W'], fallback: 'M' },
    { key: 'top_n', selector: '#analysis-top-n', type: 'integer', min: 1, max: 100, fallback: 20 },
    { key: 'weighting', selector: '#analysis-weighting', type: 'enum', allowed: ['score', 'equal'], fallback: 'score' },
    { key: 'factor_preset', selector: '#analysis-factor-preset', type: 'enum', allowed: ['zoo', 'core'], fallback: 'zoo' },
    { key: 'factor_allowlist', selector: '#analysis-factor-allowlist', type: 'factor_allowlist', fallback: '' },
    { key: 'min_market_cap', selector: '#analysis-min-market-cap', type: 'number', min: 0, max: 1e15, fallback: 10000000000 },
    { key: 'min_dollar_volume', selector: '#analysis-min-dollar-volume', type: 'number', min: 0, max: 1e15, fallback: 50000000 },
    { key: 'eligibility_adv_window', selector: '#analysis-adv-window', type: 'integer', min: 5, max: 252, fallback: 63 },
    { key: 'transaction_cost_bps', selector: '#analysis-transaction-cost', type: 'number', min: 0, max: 1000, fallback: 5 },
    { key: 'transaction_cost_model', selector: '#analysis-cost-model', type: 'enum', allowed: ['one_way_notional', 'portfolio_turnover'], fallback: 'one_way_notional' },
  ];
  const BOOTSTRAP_ANALYSIS_CONFIG = Object.freeze(Object.fromEntries(
    ANALYSIS_INPUTS.map(({ key, fallback }) => [key, fallback])
  ));
  const THEME_STORAGE_KEY = 'quant-research-theme';
  const LEGACY_THEME_STORAGE_KEYS = [
    'best-factor-theme',
    'quant-dashboard-theme',
    'quant-calm-theme',
    'dram-price-theme',
    'etf-tracking-theme',
    'sox-theme',
    'momentum-factor-theme',
  ];
  const UPDATE_AUTOMATION_DEFAULT = {
    timezone: 'Asia/Seoul',
    primary_refresh_kst: '07:00 Tue-Sat',
    fallback_refresh_kst: [
      '09:00 Tue-Sat stale/missing JSON only',
      '11:00 Tue-Sat stale/missing JSON only',
      '13:00 Tue-Sat stale/missing JSON only'
    ],
    fallback_policy: 'Primary scheduled runs refresh after each expected US regular session; fallback schedules rerun only when deployed JSON is stale, missing, or broken. workflow_dispatch remains available for reviewed reruns.',
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
  const state = {
    payload: null,
    sortMetric: 'composite_score',
    topN: RANKING_DEFAULT_TOP,
    filter: '',
    selectedFactors: new Set(),
    analysisDefaults: null,
    analysisConfigSource: 'bootstrap',
    analysisConfigHash: '',
    analysisConfigBindingStatus: 'checking',
    comparisonChart: {
      pinnedSeriesKey: 'best',
      previewSeriesKey: null,
      pinnedDate: null,
      previewDate: null,
    },
  };

  const q = (selector) => document.querySelector(selector);

  document.addEventListener('DOMContentLoaded', () => {
    bindThemeToggle();
    revealCurrentNavItem();
    bindControls();
    loadDashboard();
  });

  function revealCurrentNavItem() {
    const active = document.querySelector('.site-nav-links [aria-current="page"]');
    const rail = active?.closest?.('.site-nav-links');
    if (!active || !rail) return;
    window.requestAnimationFrame?.(() => {
      if (rail.scrollWidth <= rail.clientWidth) return;
      rail.scrollLeft = Math.max(0, active.offsetLeft - (rail.clientWidth - active.offsetWidth) / 2);
    });
  }

  function storedTheme() {
    try {
      const canonical = window.localStorage?.getItem(THEME_STORAGE_KEY);
      if (canonical === 'light' || canonical === 'dark') return canonical;
      for (const key of LEGACY_THEME_STORAGE_KEYS) {
        const legacy = window.localStorage?.getItem(key);
        if (legacy !== 'light' && legacy !== 'dark') continue;
        window.localStorage?.setItem(THEME_STORAGE_KEY, legacy);
        return legacy;
      }
      return null;
    } catch (_) {
      return null;
    }
  }

  function requestedTheme() {
    try {
      const theme = new URLSearchParams(window.location?.search || '').get('theme');
      return theme === 'light' || theme === 'dark' ? theme : null;
    } catch (_) {
      return null;
    }
  }

  function systemTheme() {
    try {
      return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    } catch (_) {
      return 'light';
    }
  }

  function saveTheme(theme) {
    try {
      window.localStorage?.setItem(THEME_STORAGE_KEY, theme);
    } catch (_) {
      // Theme persistence is optional; the dashboard still works without localStorage.
    }
  }

  function themeRoot() {
    return document.documentElement || document.querySelector?.('html') || null;
  }

  function currentTheme() {
    const root = themeRoot();
    return root?.dataset?.theme || root?.getAttribute?.('data-theme') || 'light';
  }

  function applyTheme(theme) {
    const normalized = theme === 'dark' ? 'dark' : 'light';
    const root = themeRoot();
    if (root?.dataset) {
      root.dataset.theme = normalized;
    } else if (root?.setAttribute) {
      root.setAttribute('data-theme', normalized);
    }
    if (root?.style) root.style.colorScheme = normalized;
    const button = document.querySelector('#theme-toggle');
    if (!button) return;
    const isDark = normalized === 'dark';
    button.setAttribute('aria-pressed', String(isDark));
    button.setAttribute('aria-label', isDark ? '라이트 모드로 전환' : '다크 모드로 전환');
    const label = typeof button.querySelector === 'function' ? button.querySelector('.theme-toggle-text') : null;
    if (label) label.textContent = isDark ? '라이트 모드' : '다크 모드';
  }

  function bindThemeToggle() {
    applyTheme(requestedTheme() || storedTheme() || systemTheme());
    const button = document.querySelector('#theme-toggle');
    if (!button || typeof button.addEventListener !== 'function') return;
    button.addEventListener('click', () => {
      const nextTheme = currentTheme() === 'dark' ? 'light' : 'dark';
      applyTheme(nextTheme);
      saveTheme(nextTheme);
    });
  }

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
    const analysisForm = q('#analysis-settings-form');
    const analysisCopyButton = q('#copy-analysis-command');
    const analysisResetButton = q('#reset-analysis-settings');
    const analysisWorkflowLink = q('#analysis-workflow-link');
    const heroHoldingsLink = q('#hero-holdings-link');

    if (sortSelect) {
      sortSelect.addEventListener('change', (event) => {
        state.sortMetric = event.target.value;
        renderAll();
      });
    }
    if (topInput) {
      topInput.addEventListener('input', (event) => {
        const maxRows = maxDisplayHoldings(state.payload);
        state.topN = Math.max(1, Math.min(maxRows, Number(event.target.value) || Math.min(RANKING_DEFAULT_TOP, maxRows)));
        event.target.value = String(state.topN);
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
    if (analysisWorkflowLink) analysisWorkflowLink.href = WORKFLOW_URL;
    if (analysisForm) {
      analysisForm.addEventListener('input', updateAnalysisWorkflowCommand);
      analysisForm.addEventListener('change', updateAnalysisWorkflowCommand);
      analysisForm.addEventListener('submit', (event) => event.preventDefault());
    }
    if (analysisCopyButton) analysisCopyButton.addEventListener('click', copyAnalysisWorkflowCommand);
    if (analysisResetButton) analysisResetButton.addEventListener('click', resetAnalysisSettings);
    if (heroHoldingsLink) {
      heroHoldingsLink.addEventListener('click', (event) => {
        const disclosure = q('#secondary-results');
        const target = q('#current-output-title');
        if (!disclosure || !target) return;
        event.preventDefault();
        disclosure.open = true;
        window.requestAnimationFrame?.(() => target.scrollIntoView?.({ behavior: 'smooth', block: 'start' }));
      });
    }
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

  async function copyAnalysisWorkflowCommand() {
    const status = q('#analysis-command-status');
    try {
      const config = readAnalysisSettingsForm();
      const command = buildAnalysisWorkflowCommand(config);
      if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('clipboard unavailable');
      await navigator.clipboard.writeText(command);
      if (status) status.textContent = '명령을 복사했습니다. 실행이 완료되면 이 설정이 다음 자동 갱신에도 사용됩니다.';
    } catch (error) {
      if (status) status.textContent = error.message === 'clipboard unavailable'
        ? '브라우저에서 복사할 수 없습니다. 위 명령을 직접 선택해 복사하세요.'
        : `입력값을 확인하세요. ${error.message}`;
    }
  }

  async function loadAnalysisConfigSidecar(payload) {
    let sidecar;
    try {
      const response = await fetch(ANALYSIS_CONFIG_URL, { cache: 'no-store' });
      if (!response.ok) {
        return { config: null, source: 'bootstrap', configHash: '', bindingStatus: 'missing' };
      }
      sidecar = await response.json();
    } catch (_) {
      return { config: null, source: 'bootstrap', configHash: '', bindingStatus: 'invalid' };
    }
    try {
      if (sidecar.schema_version !== undefined && sidecar.schema_version !== 1) {
        throw new Error(`unsupported config schema ${sidecar.schema_version}`);
      }
      const rawConfig = sidecar.config || sidecar;
      const missing = ANALYSIS_INPUTS
        .map(({ key }) => key)
        .filter((key) => !Object.prototype.hasOwnProperty.call(rawConfig || {}, key));
      if (missing.length) throw new Error(`missing fields: ${missing.join(',')}`);
      const binding = validateResultBinding(sidecar.result_binding, payload);
      if (!binding.valid) {
        return { config: null, source: 'bootstrap', configHash: '', bindingStatus: binding.status };
      }
      return {
        config: normalizeAnalysisConfig(canonicalAnalysisRaw(rawConfig)),
        source: 'sidecar',
        configHash: String(sidecar.config_hash || ''),
        bindingStatus: 'bound',
      };
    } catch (_) {
      return { config: null, source: 'bootstrap', configHash: '', bindingStatus: 'invalid' };
    }
  }

  function validateResultBinding(resultBinding, payload) {
    const summary = payload?.summary || {};
    const metadata = payload?.metadata || {};
    const expected = {
      generated_at: payload?.generated_at,
      source_hash: summary.source_hash || metadata.source_hash,
      data_end_date: summary.data_end_date || metadata.data_end_date,
    };
    const keys = Object.keys(expected);
    if (!resultBinding || typeof resultBinding !== 'object') return { valid: false, status: 'missing' };
    const bindingKeys = Object.keys(resultBinding);
    if (bindingKeys.length !== keys.length || bindingKeys.some((key) => !keys.includes(key))) {
      return { valid: false, status: 'invalid' };
    }
    if (keys.some((key) => !expected[key] || !resultBinding[key])) return { valid: false, status: 'missing' };
    const mismatch = keys.some((key) => String(resultBinding[key]) !== String(expected[key]));
    return mismatch ? { valid: false, status: 'mismatch' } : { valid: true, status: 'bound' };
  }

  function analysisConfigFromPayload(payload) {
    const metadata = payload.metadata || {};
    const explicit = metadata.applied_config || metadata.applied_analysis_config || metadata.analysis_config || payload.analysis_config || {};
    const hasCompleteExplicitConfig = ANALYSIS_INPUTS
      .map(({ key }) => key)
      .every((key) => Object.prototype.hasOwnProperty.call(explicit || {}, key));
    if (!hasCompleteExplicitConfig) return normalizeAnalysisConfig(BOOTSTRAP_ANALYSIS_CONFIG, true);
    const factorAllowlist = firstDefined(explicit.factor_allowlist, explicit.factors, '');
    return normalizeAnalysisConfig({
      period: explicit.period,
      rebalance: explicit.rebalance,
      top_n: explicit.top_n,
      weighting: explicit.weighting,
      factor_preset: explicit.factor_preset === 'explicit'
        ? firstDefined(explicit.requested_factor_preset, metadata.requested_factor_preset, 'zoo')
        : explicit.factor_preset,
      factor_allowlist: Array.isArray(factorAllowlist) ? factorAllowlist.join(',') : factorAllowlist,
      min_market_cap: explicit.min_market_cap,
      min_dollar_volume: explicit.min_dollar_volume,
      eligibility_adv_window: explicit.eligibility_adv_window,
      transaction_cost_bps: explicit.transaction_cost_bps,
      transaction_cost_model: explicit.transaction_cost_model,
    });
  }

  function firstDefined(...values) {
    return values.find((value) => value !== null && value !== undefined && value !== '');
  }

  function canonicalAnalysisRaw(rawConfig) {
    const raw = rawConfig || {};
    if (raw.factor_preset !== 'explicit') return raw;
    return {
      ...raw,
      factor_preset: firstDefined(raw.requested_factor_preset, 'zoo'),
    };
  }

  function normalizeAnalysisConfig(rawConfig, allowFallback = false) {
    const raw = rawConfig || {};
    return Object.fromEntries(ANALYSIS_INPUTS.map((spec) => [
      spec.key,
      normalizeAnalysisValue(spec, raw[spec.key], allowFallback),
    ]));
  }

  function normalizeAnalysisValue(spec, rawValue, allowFallback) {
    const blank = rawValue === null || rawValue === undefined || String(rawValue).trim() === '';
    if (spec.type === 'factor_allowlist') {
      if (blank) return '';
      if (String(rawValue).trim() === '__preset__') return '';
      const names = String(rawValue).split(',').map((name) => name.trim()).filter(Boolean);
      if (!names.length) return '';
      if (names.some((name) => !/^[A-Za-z0-9_]+$/.test(name))) {
        throw new Error('직접 선택 팩터는 영문, 숫자, 밑줄과 쉼표만 사용할 수 있습니다.');
      }
      return Array.from(new Set(names)).join(',');
    }
    if (blank) {
      if (allowFallback) return spec.fallback;
      throw new Error(`${spec.key} 값이 비어 있습니다.`);
    }
    if (spec.type === 'enum') {
      const value = String(rawValue);
      if (!spec.allowed.includes(value)) throw new Error(`${spec.key} 값이 허용 범위를 벗어났습니다.`);
      return value;
    }
    const numeric = Number(rawValue);
    if (!Number.isFinite(numeric)) throw new Error(`${spec.key} 값은 숫자여야 합니다.`);
    if (spec.type === 'integer' && !Number.isInteger(numeric)) throw new Error(`${spec.key} 값은 정수여야 합니다.`);
    if (numeric < spec.min || numeric > spec.max) throw new Error(`${spec.key} 값은 ${spec.min}~${spec.max} 범위여야 합니다.`);
    return numeric;
  }

  function buildAnalysisWorkflowCommand(rawConfig) {
    const config = normalizeAnalysisConfig(rawConfig);
    const fields = ANALYSIS_INPUTS.map(({ key }) => {
      const value = key === 'factor_allowlist' && !config[key] ? '__preset__' : config[key];
      return `--raw-field '${key}=${value}'`;
    });
    return [WORKFLOW_COMMAND, ...fields].join(' ');
  }

  function readAnalysisSettingsForm() {
    const values = {};
    ANALYSIS_INPUTS.forEach(({ key, selector }) => {
      const input = q(selector);
      values[key] = input ? input.value : '';
    });
    return normalizeAnalysisConfig(values);
  }

  function writeAnalysisSettingsForm(rawConfig) {
    const config = normalizeAnalysisConfig(rawConfig, true);
    ANALYSIS_INPUTS.forEach(({ key, selector }) => {
      const input = q(selector);
      if (input) input.value = String(config[key]);
    });
    const factorInput = q('#analysis-factor-allowlist');
    if (factorInput) factorInput.setCustomValidity('');
    updateAnalysisWorkflowCommand();
  }

  function updateAnalysisWorkflowCommand() {
    const commandNode = q('#analysis-workflow-command');
    const copyButton = q('#copy-analysis-command');
    const status = q('#analysis-command-status');
    const factorInput = q('#analysis-factor-allowlist');
    try {
      const config = readAnalysisSettingsForm();
      const command = buildAnalysisWorkflowCommand(config);
      if (commandNode) commandNode.textContent = command;
      if (copyButton) copyButton.disabled = false;
      if (factorInput) factorInput.setCustomValidity('');
      if (status) status.textContent = 'Actions 실행이 성공하면 이 값이 공개 분석과 다음 자동 갱신에 적용됩니다.';
    } catch (error) {
      if (commandNode) commandNode.textContent = '입력값을 확인하면 명령이 생성됩니다.';
      if (copyButton) copyButton.disabled = true;
      if (factorInput) {
        const factorError = String(error.message || '').includes('직접 선택 팩터') ? error.message : '';
        factorInput.setCustomValidity(factorError);
      }
      if (status) status.textContent = error.message;
    }
  }

  function resetAnalysisSettings() {
    if (!state.analysisDefaults) return;
    writeAnalysisSettingsForm(state.analysisDefaults);
    const status = q('#analysis-command-status');
    if (status) status.textContent = state.analysisConfigBindingStatus === 'bound'
      ? '현재 공개 결과에 적용된 설정으로 되돌렸습니다.'
      : '확인용 기본 설정으로 되돌렸습니다.';
  }

  function renderAppliedAnalysisConfig(payload) {
    const root = q('#applied-config-summary');
    if (!root) return;
    const metadata = payload.metadata || {};
    const summary = payload.summary || {};
    const config = state.analysisDefaults || analysisConfigFromPayload(payload);
    const factorNames = String(config.factor_allowlist || '').split(',').filter(Boolean);
    const factorValue = factorNames.length
      ? `직접 ${factorNames.length}개`
      : `${String(config.factor_preset).toUpperCase()} · ${summary.selected_factor_count ?? metadata.selected_factor_count ?? '—'}개`;
    const marketCapValue = marketCapDisplay(config, metadata);
    const chips = [
      ['기간', config.period],
      ['리밸런싱', config.rebalance === 'W' ? '주간' : '월간'],
      ['편입 상한', `${config.top_n}종목`],
      ['가중', config.weighting === 'equal' ? '동일가중' : '점수가중'],
      ['팩터', factorValue],
      ['최소 시총', marketCapValue],
      ['최소 ADV', fmtUsd(config.min_dollar_volume)],
      ['ADV 관찰', `${config.eligibility_adv_window}일`],
      ['거래비용', `${config.transaction_cost_bps}bps · ${costModelLabel(config.transaction_cost_model)}`],
    ];
    root.replaceChildren(...chips.map(([label, value]) => {
      const item = el('span', 'applied-config-item');
      item.append(small(label), strong(value));
      return item;
    }));
    const bindingValid = state.analysisConfigBindingStatus === 'bound';
    const status = q('#applied-config-status');
    setText('#applied-config-title', bindingValid ? '현재 결과에 적용된 설정' : '분석 설정 기준값');
    if (status) {
      status.hidden = bindingValid;
      status.textContent = bindingStatusText(state.analysisConfigBindingStatus);
      status.classList.toggle('is-warning', !bindingValid);
    }
    const configHash = bindingValid && state.analysisConfigHash ? ` · 설정 ${state.analysisConfigHash.slice(0, 8)}` : '';
    setText(
      '#applied-config-date',
      `결과 기준 ${summary.data_end_date || metadata.data_end_date || payload.data_scope}${configHash}`
    );
  }

  function marketCapDisplay(config, metadata) {
    const minimum = Number(config?.min_market_cap);
    if (minimum === 0) return '없음';
    if (metadata?.market_cap_filter_effective === false) {
      return `요청 ${fmtUsd(minimum)} · 이번 실행 미적용`;
    }
    return Number.isFinite(minimum) && minimum > 0 ? fmtUsd(minimum) : '없음';
  }

  function bindingStatusText(status) {
    const labels = {
      bound: '설정 연결 완료',
      mismatch: '설정 연결 확인 필요 · 결과 불일치',
      missing: '설정 연결 확인 필요 · 설정 없음',
      invalid: '설정 연결 확인 필요 · 파일 오류',
      checking: '설정 연결 확인 중',
    };
    return labels[status] || labels.invalid;
  }

  function costModelLabel(model) {
    return model === 'portfolio_turnover' ? '회전율' : '편도 매매금액';
  }

  async function loadDashboard() {
    try {
      const response = await fetch(DATA_URL, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      if (payload.schema_version !== 1) {
        throw new Error(`지원하지 않는 dashboard schema_version: ${payload.schema_version ?? 'missing'}`);
      }
      const analysisConfig = await loadAnalysisConfigSidecar(payload);
      state.payload = payload;
      state.analysisDefaults = analysisConfig.config || analysisConfigFromPayload(payload);
      state.analysisConfigSource = analysisConfig.source;
      state.analysisConfigHash = analysisConfig.configHash || '';
      state.analysisConfigBindingStatus = analysisConfig.bindingStatus || 'invalid';
      writeAnalysisSettingsForm(state.analysisDefaults);
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
    renderAppliedAnalysisConfig(payload);
    syncDisplayControls(payload);
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
    renderMetrics(payload);
    renderMetadata(payload);
    renderCaveats(payload);
    enableTableDrag();
    enableScrollPanels();
  }

  function enableTableDrag() {
    document.querySelectorAll('.table-wrap, .performance-table-wrap').forEach((wrap) => {
      if (wrap.dataset.dragScrollBound === 'true') return;
      wrap.dataset.dragScrollBound = 'true';
      if (!wrap.getAttribute('tabindex')) wrap.setAttribute('tabindex', '0');
      if (!wrap.getAttribute('aria-label')) wrap.setAttribute('aria-label', '가로로 드래그해 전체 표 보기');
      const drag = { active: false, startX: 0, startScrollLeft: 0 };
      wrap.addEventListener('pointerdown', (event) => {
        if (event.button !== 0 || wrap.scrollWidth <= wrap.clientWidth) return;
        if (event.target && event.target.closest && event.target.closest('a, button, input, select, textarea, summary')) return;
        drag.active = true;
        drag.startX = event.clientX;
        drag.startScrollLeft = wrap.scrollLeft;
        wrap.classList.add('is-dragging');
        if (wrap.setPointerCapture) wrap.setPointerCapture(event.pointerId);
      });
      wrap.addEventListener('pointermove', (event) => {
        if (!drag.active) return;
        wrap.scrollLeft = drag.startScrollLeft - (event.clientX - drag.startX);
      });
      const stopDrag = (event) => {
        if (!drag.active) return;
        drag.active = false;
        wrap.classList.remove('is-dragging');
        if (wrap.releasePointerCapture) wrap.releasePointerCapture(event.pointerId);
      };
      wrap.addEventListener('pointerup', stopDrag);
      wrap.addEventListener('pointercancel', stopDrag);
      wrap.addEventListener('mouseleave', () => {
        drag.active = false;
        wrap.classList.remove('is-dragging');
      });
      wrap.addEventListener('keydown', (event) => {
        const lineStep = 64;
        const pageStep = Math.max(160, wrap.clientHeight * 0.8);
        let handled = true;
        if (event.key === 'ArrowRight') wrap.scrollLeft += lineStep;
        else if (event.key === 'ArrowLeft') wrap.scrollLeft -= lineStep;
        else if (event.key === 'ArrowDown' && wrap.scrollHeight > wrap.clientHeight) wrap.scrollTop += lineStep;
        else if (event.key === 'ArrowUp' && wrap.scrollHeight > wrap.clientHeight) wrap.scrollTop -= lineStep;
        else if (event.key === 'PageDown' && wrap.scrollHeight > wrap.clientHeight) wrap.scrollTop += pageStep;
        else if (event.key === 'PageUp' && wrap.scrollHeight > wrap.clientHeight) wrap.scrollTop -= pageStep;
        else handled = false;
        if (handled) event.preventDefault();
      });
    });
  }

  function enableScrollPanels() {
    document.querySelectorAll('.scroll-panel').forEach((panel) => {
      if (panel.dataset.scrollPanelBound === 'true') return;
      panel.dataset.scrollPanelBound = 'true';
      if (!panel.getAttribute('tabindex')) panel.setAttribute('tabindex', '0');
      panel.addEventListener('keydown', (event) => {
        if (panel.scrollHeight <= panel.clientHeight) return;
        const lineStep = 72;
        const pageStep = Math.max(180, panel.clientHeight * 0.82);
        let handled = true;
        if (event.key === 'ArrowDown') panel.scrollTop += lineStep;
        else if (event.key === 'ArrowUp') panel.scrollTop -= lineStep;
        else if (event.key === 'PageDown') panel.scrollTop += pageStep;
        else if (event.key === 'PageUp') panel.scrollTop -= pageStep;
        else if (event.key === 'Home') panel.scrollTop = 0;
        else if (event.key === 'End') panel.scrollTop = panel.scrollHeight;
        else handled = false;
        if (handled) event.preventDefault();
      });
    });
  }

  function renderStatus(payload) {
    const summary = payload.summary || {};
    const holdout = summary.best_factor_holdout_rank ? `#${summary.best_factor_holdout_rank}` : '—';
    const lines = [
      statusLine('데이터 기준', summary.data_end_date || payload.data_scope),
      statusLine('Holdout', holdout),
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
    const bestMetrics = metricForFactor(payload, summary.best_factor) || (payload.rankings || [])[0] || {};
    const cards = [
      ['현재 1위 팩터', summary.best_factor, '공식 종합 점수 기준'],
      ['종합 점수', fmtNumber(summary.best_composite_score, 4), '성과·위험 합산'],
      ['CAGR', fmtPct(bestMetrics.cagr), '전체 평가기간'],
      ['Sharpe', fmtNumber(bestMetrics.sharpe, 2), '위험조정 성과'],
      ['MDD', fmtPct(bestMetrics.max_drawdown), '최대 낙폭'],
    ];
    const nodes = cards.map(([label, value, help], index) => card(label, value, help, index === 0 ? '현재 1위' : ''));
    if (nodes[0]) nodes[0].classList.add('result-card-primary');
    q('#summary-cards').replaceChildren(...nodes);
  }

  function renderUpdatePanel(payload) {
    const automation = automationConfig(payload);
    const scheduleList = q('#update-schedule-list');
    if (scheduleList) {
      scheduleList.replaceChildren(
        scheduleItem('07:00 KST Tue-Sat', '직전 미국 정규장 기준 live-data run.'),
        scheduleItem('09/11/13 KST fallback', 'JSON stale/missing/broken일 때만 재실행.'),
        scheduleItem('검토 후 수동 재실행', 'workflow_dispatch로 동일 검증 경로 실행.')
      );
    }
    setText('#update-status', `${updateScheduleText(payload)} · 수동 재실행은 GitHub Actions workflow_dispatch 권한이 필요합니다.`);
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
    const implementation = portfolioDiagnostics(payload);
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
      analysisCard('성과와 위험의 균형', '종합 점수는 수익률과 위험조정 지표를 함께 봅니다.', [
        ['CAGR', fmtPct(metrics.cagr)],
        ['Sharpe / Sortino', `${fmtNumber(metrics.sharpe, 2)} / ${fmtNumber(metrics.sortino, 2)}`],
        ['Calmar / MDD', `${fmtNumber(metrics.calmar, 2)} / ${fmtPct(metrics.max_drawdown)}`],
      ]),
      analysisCard('견고성 체크', '최근 tail holdout은 보조 검증입니다.', [
        ['Holdout', holdout],
        ['Coverage', fmtPct(metrics.coverage)],
        ['Turnover', fmtPct(metrics.turnover)],
      ]),
      analysisCard('실행 전 점검', '실제 운용 전 체결, 비용, 집중도, 유동성을 별도 확인해야 합니다.', [
        ['보유 종목 수', holdings.length],
        ['유효 보유 종목 수', fmtNumber(implementation.effectiveHoldings, 1)],
        ['최대 / Top5 비중', `${fmtPct(topWeight)} / ${fmtPct(implementation.top5Weight)}`],
        ['10% ADV 용량 추정', `${fmtUsd(implementation.capacity10)} · 제한 종목 ${fmtText(implementation.capacityLimitTicker)}`],
        ['평균 / 최근 회전율', `${fmtPct(implementation.averageTurnover)} / ${fmtPct(implementation.latestTurnover)}`],
        ['비중 합계', fmtPct(totalWeight)],
      ])
    );
  }

  function renderDiagnostics(payload) {
    const summary = payload.summary || {};
    const metadata = payload.metadata || {};
    const skipped = payload.skipped_reasons || [];
    const implementation = portfolioDiagnostics(payload);
    q('#diagnostics-grid').replaceChildren(
      diagnosticCard('데이터 커버리지', [
        ['JSON 생성', payload.generated_at],
        ['원천 fetch/run', summary.fetched_at || 'metadata missing'],
        ['Universe 기준일', summary.universe_as_of_date || 'unknown'],
        ['Universe 범위', metadata.universe_scope_note || 'curated/current ticker set'],
        ['Data scope', payload.data_scope || 'unknown'],
        ['Provider', summary.provider || metadata.provider || 'unknown'],
        ['Provider chain', metadata.provider_order || metadata.provider_attempted_sources || '단일 경로'],
        ['Fill counts', metadata.provider_fill_counts || 'unknown'],
        ['Fallback filled', metadata.fallback_filled_ticker_count ?? 0],
      ]),
      diagnosticListCard('팩터/랭킹 게이트', [
        gateItem('팩터 프리셋', summary.factor_preset || metadata.factor_preset || 'unknown', 'pass'),
        gateItem('라이브러리 후보', `${summary.factor_library_size ?? metadata.factor_library_size ?? 'unknown'}개`, Number(summary.factor_library_size ?? metadata.factor_library_size) >= 300 ? 'pass' : 'warn'),
        gateItem('선택 후보', `${summary.selected_factor_count ?? metadata.selected_factor_count ?? summary.tested_factor_count ?? 'unknown'}개`, Number(summary.selected_factor_count ?? metadata.selected_factor_count ?? summary.tested_factor_count) >= 300 ? 'pass' : 'warn'),
        gateItem('분석 주식 수', `${metadata.price_ticker_count ?? 'unknown'} / 요청 ${metadata.requested_ticker_count ?? 'unknown'}개 · 랭크 가능 ${metadata.rankable_stock_universe_count ?? 'unknown'}개`, Number(metadata.price_ticker_count) >= Number(metadata.min_price_tickers || 500) ? 'pass' : 'warn'),
        gateItem('가격 커버리지', `${fmtPct(metadata.price_coverage_ratio)} · 최신 기준일 ${fmtText(metadata.latest_data_reference_date || metadata.data_end_date)} ${fmtPct(metadata.latest_data_coverage_ratio)}`, Number(metadata.price_coverage_ratio) >= Number(metadata.min_price_coverage_ratio || 0.9) && Number(metadata.latest_data_coverage_ratio) >= Number(metadata.min_latest_data_coverage_ratio || 0.9) ? 'pass' : 'warn'),
        gateItem(
          '데이터 소스 대비책',
          `${fmtText(metadata.provider_attempted_sources || metadata.provider_order || [summary.provider || metadata.provider || 'unknown'])} · fallback fill ${metadata.fallback_filled_ticker_count ?? 0}개 · provider errors ${metadata.provider_error_count ?? 0}개`,
          Number(metadata.provider_error_count || 0) === 0 ? 'pass' : 'warn'
        ),
        gateItem('실질 후보 수', `${metadata.latest_factor_eligible_ticker_count ?? 'unknown'} / 최소 ${metadata.min_factor_eligible_tickers ?? 'none'}개 · history ${metadata.history_qualified_ticker_count ?? 'unknown'} · liquidity ${metadata.liquidity_qualified_ticker_count ?? 'unknown'}`, Number(metadata.latest_factor_eligible_ticker_count) >= Number(metadata.min_factor_eligible_tickers || 0) ? 'pass' : 'warn'),
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
        ...(metadata.market_cap_filter_status ? [gateItem('시가총액 필터 상태', metadata.market_cap_filter_status, metadata.market_cap_filter_effective ? 'pass' : 'warn')] : []),
        ...(metadata.transaction_cost_note ? [gateItem('거래비용 모델', `${metadata.transaction_cost_bps ?? 0}bps · ${metadata.transaction_cost_model || 'unknown'} · ${metadata.transaction_cost_note}`, 'pass')] : []),
        ...(metadata.factor_eligibility_note ? [gateItem('실질 후보 진단', metadata.factor_eligibility_note, 'pass')] : []),
        ...(skipped.length ? skipped.map((row) => gateItem(row.skip_reason, `${row.count}개`, 'warn')) : [gateItem('스킵 사유', '없음', 'pass')]),
      ]),
      diagnosticListCard('실무 운용 진단', [
        gateItem(
          '집중도',
          `유효 보유 ${fmtNumber(implementation.effectiveHoldings, 1)}개 · 최대 단일 ${fmtPct(implementation.maxWeight)} · Top5 ${fmtPct(implementation.top5Weight)} · 비중합 ${fmtPct(implementation.weightSum)}`,
          Number(implementation.effectiveHoldings) >= Math.min(10, Number(metadata.latest_portfolio_holding_count || 20) * 0.5) ? 'pass' : 'warn'
        ),
        gateItem(
          '유동성',
          `최소 ADV ${fmtUsd(implementation.minAdv)} (${fmtText(implementation.minAdvTicker)}) · 가중 ADV ${fmtUsd(implementation.weightedAdv)} · ${implementation.advWindow || '—'}일 평균`,
          Number(implementation.minAdv) >= Number(metadata.eligibility_min_dollar_volume || 0) ? 'pass' : 'warn'
        ),
        gateItem(
          '용량 추정',
          `5% ADV ${fmtUsd(implementation.capacity5)} · 10% ADV ${fmtUsd(implementation.capacity10)} · 제한 종목 ${fmtText(implementation.capacityLimitTicker)}`,
          Number.isFinite(Number(implementation.capacity10)) && Number(implementation.capacity10) > 0 ? 'pass' : 'warn'
        ),
        gateItem(
          '회전율/거래비용',
          `평균 turnover ${fmtPct(implementation.averageTurnover)} · 최근 ${fmtPct(implementation.latestTurnover)} · 비용 ${metadata.transaction_cost_bps ?? 0}bps ${metadata.transaction_cost_model || 'unknown'}`,
          'pass'
        ),
        gateItem(
          '용량 해석 한계',
          metadata.latest_portfolio_capacity_note || 'ADV 기반 휴리스틱일 뿐 호가/시장충격/세금/대차/브로커 체결 모델이 아닙니다.',
          'warn'
        ),
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
    const catalog = factorCatalog(payload);
    const catalogByCategory = new Map();
    catalog.forEach((item) => {
      const category = String(item.category || 'unknown');
      if (!catalogByCategory.has(category)) catalogByCategory.set(category, []);
      catalogByCategory.get(category).push(item);
    });
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
      const familyCatalog = catalogByCategory.get(String(family.category || 'unknown')) || [];
      const sampleNames = new Set((family.examples || []).slice(0, 6).map((name) => String(name)));
      const samples = [
        ...familyCatalog.filter((item) => sampleNames.has(String(item.name))),
        ...familyCatalog.filter((item) => !sampleNames.has(String(item.name))),
      ].slice(0, 4);
      const details = el('details', 'factor-method-details');
      const summaryEl = el('summary', 'factor-method-summary');
      summaryEl.textContent = '계산법/예시 팩터 보기';
      const methodList = el('div', 'factor-method-list');
      samples.forEach((item) => {
        const method = factorMethodDetails(item);
        const row = el('div', 'factor-method-row');
        row.append(
          strong(fmtText(item.name)),
          small(`산식: ${method.formula}`),
          small(`해석: ${method.method}`),
          small(`파라미터: ${method.params}`)
        );
        methodList.append(row);
      });
      if (!samples.length) methodList.append(small('이 팩터군의 세부 카탈로그가 없습니다.'));
      details.append(summaryEl, methodList);
      const examples = el('div', 'factor-examples');
      (family.examples || []).slice(0, 6).forEach((name) => examples.append(span(name, 'factor-pill')));
      article.append(meta, details, examples);
      return article;
    }));
  }

  function renderFactorReturnChart(payload) {
    const rows = visibleRankings(payload).slice(0, 8);
    const officialBest = String((payload.summary || {}).best_factor || '');
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
      best: String(row.factor || '') === officialBest,
      selected: state.selectedFactors.has(String(row.factor || '')),
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

  function maxDisplayHoldings(payload) {
    const available = Array.isArray(payload?.latest_holdings) ? payload.latest_holdings.length : 0;
    return Math.max(1, available || RANKING_DEFAULT_TOP);
  }

  function syncDisplayControls(payload) {
    const input = q('#topn-input');
    const available = maxDisplayHoldings(payload);
    state.topN = Math.max(1, Math.min(state.topN, available));
    if (input) {
      input.max = String(available);
      input.value = String(state.topN);
    }
    setText('#holding-display-help', `저장된 결과 중 최대 ${available}행 · 화면에만 적용`);
  }

  function renderWeightChart(payload) {
    const holdings = (payload.latest_holdings || []).slice(0, Math.min(state.topN, 12));
    setText('#weight-chart-meta', `${holdings.length}개 표시 · 표시 비중 합계 ${fmtPct(sumWeights(holdings))}`);
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
    const available = (payload.latest_holdings || []).length;
    setText('#current-output-meta', `${holdings.length}/${available}행 표시 · 기준 ${fmtText((payload.summary || {}).data_end_date)}`);
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
      `공식 1위 ${bestFactor || '—'} · 차트 비교 ${selectedFactor || '—'} · ${benchmarkSeries.label}`
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
    const label = (rows[0] || {}).benchmark || metadata.benchmark_label || 'Nasdaq Composite';
    const ticker = (rows[0] || {}).ticker || (Array.isArray(metadata.benchmark_tickers) ? metadata.benchmark_tickers[0] : '');
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
    const plot = { left: 86, right: 24, top: 22, bottom: 58 };
    const plotWidth = width - plot.left - plot.right;
    const plotHeight = height - plot.top - plot.bottom;
    const xFor = (date) => plot.left + (allDates.length <= 1 ? 0 : (dateToIndex.get(date) || 0) / (allDates.length - 1) * plotWidth);
    const yFor = (equity) => height - plot.bottom - ((equity - minValue) / Math.max(0.000001, maxValue - minValue)) * plotHeight;
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('aria-hidden', 'true');

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
    appendSvgText(svg, '누적 수익률', plot.left, 14, 'axis-title', 'start');

    const paths = [];
    seriesList.forEach((series) => {
      const points = series.points.map((point) => `${xFor(point.date).toFixed(1)},${yFor(point.equity).toFixed(1)}`).join(' ');
      if (!points) return;
      const polyline = document.createElementNS(SVG_NS, 'polyline');
      polyline.setAttribute('points', points);
      polyline.setAttribute('class', `comparison-line ${series.key}`);
      polyline.setAttribute('data-series-key', series.key);
      svg.appendChild(polyline);
      paths.push(polyline);
    });

    const dateGuide = document.createElementNS(SVG_NS, 'line');
    dateGuide.setAttribute('y1', String(plot.top));
    dateGuide.setAttribute('y2', String(height - plot.bottom));
    dateGuide.setAttribute('class', 'chart-date-guide');
    svg.appendChild(dateGuide);

    const activePoint = document.createElementNS(SVG_NS, 'circle');
    activePoint.setAttribute('r', '5.5');
    activePoint.setAttribute('class', 'chart-active-point best');
    svg.appendChild(activePoint);

    const hitTarget = document.createElementNS(SVG_NS, 'rect');
    hitTarget.setAttribute('x', String(plot.left));
    hitTarget.setAttribute('y', String(plot.top));
    hitTarget.setAttribute('width', String(plotWidth));
    hitTarget.setAttribute('height', String(plotHeight));
    hitTarget.setAttribute('class', 'chart-hit-target');
    svg.appendChild(hitTarget);

    const readout = el('div', 'chart-active-readout');
    const readoutDate = span('—', 'chart-readout-date');
    const readoutSeries = span('—', 'chart-readout-series');
    const readoutValue = strong('—');
    const readoutContext = small('누적 수익률');
    readout.append(readoutDate, readoutSeries, readoutValue, readoutContext);
    root.append(svg, readout);

    const chartState = state.comparisonChart;
    const seriesKeys = seriesList.map((series) => series.key);
    if (!seriesKeys.includes(chartState.pinnedSeriesKey)) chartState.pinnedSeriesKey = seriesKeys[0];
    chartState.pinnedDate = nearestChartDate(allDates, chartState.pinnedDate || allDates.at(-1));
    chartState.previewSeriesKey = seriesKeys.includes(chartState.previewSeriesKey) ? chartState.previewSeriesKey : null;
    chartState.previewDate = chartState.previewDate ? nearestChartDate(allDates, chartState.previewDate) : null;

    const seriesControls = q('#comparison-series-controls');
    const seriesButtons = [];
    if (seriesControls) {
      seriesControls.replaceChildren(...seriesList.map((series) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `chart-series-button ${series.key}`;
        button.setAttribute('data-series-key', series.key);
        button.setAttribute('aria-pressed', String(series.key === chartState.pinnedSeriesKey));
        const key = el('span', `series-key ${series.key}`);
        const copy = el('span', 'series-button-copy');
        copy.append(strong(shortSeriesLabel(series)), small(series.sourceName || series.label));
        button.append(key, copy);
        button.title = series.label;
        button.addEventListener('pointerenter', () => {
          chartState.previewSeriesKey = series.key;
          updateActiveState();
        });
        button.addEventListener('pointerleave', () => {
          chartState.previewSeriesKey = null;
          updateActiveState();
        });
        button.addEventListener('focus', () => {
          chartState.previewSeriesKey = series.key;
          updateActiveState();
        });
        button.addEventListener('blur', () => {
          chartState.previewSeriesKey = null;
          updateActiveState();
        });
        button.addEventListener('click', () => {
          chartState.pinnedSeriesKey = series.key;
          chartState.previewSeriesKey = null;
          updateActiveState();
        });
        seriesButtons.push(button);
        return button;
      }));
    }

    const dateInput = q('#comparison-date-input');
    const latestButton = q('#comparison-latest-date');
    if (dateInput) {
      dateInput.min = allDates[0] || '';
      dateInput.max = allDates.at(-1) || '';
      dateInput.value = chartState.pinnedDate || '';
      dateInput.oninput = () => {
        chartState.previewDate = nearestChartDate(allDates, dateInput.value);
        updateActiveState();
      };
      dateInput.onchange = () => {
        chartState.pinnedDate = nearestChartDate(allDates, dateInput.value);
        chartState.previewDate = null;
        dateInput.value = chartState.pinnedDate || '';
        updateActiveState();
        ensureActiveDateVisible(chartState.pinnedDate);
      };
      dateInput.onblur = () => {
        chartState.previewDate = null;
        dateInput.value = chartState.pinnedDate || '';
        updateActiveState();
      };
    }
    if (latestButton) {
      latestButton.onclick = () => {
        chartState.pinnedDate = allDates.at(-1) || null;
        chartState.previewDate = null;
        if (dateInput) dateInput.value = chartState.pinnedDate || '';
        updateActiveState();
        ensureActiveDateVisible(chartState.pinnedDate);
      };
    }

    function updateActiveState() {
      const activeSeriesKey = seriesKeys.includes(chartState.previewSeriesKey)
        ? chartState.previewSeriesKey
        : chartState.pinnedSeriesKey;
      const activeDate = nearestChartDate(allDates, chartState.previewDate || chartState.pinnedDate || allDates.at(-1));
      const activeSeries = seriesList.find((series) => series.key === activeSeriesKey) || seriesList[0];
      const point = chartPointAtDate(activeSeries.points, activeDate);
      const guideX = xFor(activeDate);

      paths.forEach((path) => {
        const active = path.getAttribute('data-series-key') === activeSeries.key;
        path.classList.toggle('is-active', active);
        path.classList.toggle('is-muted', !active);
      });
      seriesButtons.forEach((button) => {
        const key = button.getAttribute('data-series-key');
        button.setAttribute('aria-pressed', String(key === chartState.pinnedSeriesKey));
        button.classList.toggle('is-preview', key === chartState.previewSeriesKey);
      });

      dateGuide.setAttribute('x1', String(guideX));
      dateGuide.setAttribute('x2', String(guideX));
      if (point) {
        activePoint.removeAttribute('hidden');
        activePoint.setAttribute('cx', String(xFor(point.date)));
        activePoint.setAttribute('cy', String(yFor(point.equity)));
        activePoint.setAttribute('class', `chart-active-point ${activeSeries.key}`);
      } else {
        activePoint.setAttribute('hidden', '');
      }

      readoutDate.textContent = activeDate || '—';
      setText('#comparison-date-observation', `표시 ${activeDate || '—'}`);
      readoutSeries.textContent = activeSeries.label;
      readoutValue.textContent = point ? fmtPct(Number(point.equity) - 1) : '관측 없음';
      readoutContext.textContent = `평가 시작 대비 누적 수익률 · 전체 MDD ${fmtPct(maxDrawdownFromPoints(activeSeries.points))}`;
      root.setAttribute('aria-label', `${activeDate || '선택일 없음'} ${activeSeries.label} ${point ? fmtPct(Number(point.equity) - 1) : '관측 없음'}`);
      renderComparisonValueCards(seriesList, activeDate, activeSeries.key);
    }

    function dateForClientX(clientX) {
      const rect = svg.getBoundingClientRect();
      const svgX = rect.width > 0 ? (clientX - rect.left) * (width / rect.width) : plot.left;
      const ratio = Math.max(0, Math.min(1, (svgX - plot.left) / plotWidth));
      return allDates[Math.round(ratio * Math.max(0, allDates.length - 1))] || allDates.at(-1);
    }

    hitTarget.addEventListener('pointermove', (event) => {
      chartState.previewDate = dateForClientX(event.clientX);
      updateActiveState();
    });
    hitTarget.addEventListener('pointerleave', () => {
      chartState.previewDate = null;
      updateActiveState();
    });
    hitTarget.addEventListener('click', (event) => {
      chartState.pinnedDate = dateForClientX(event.clientX);
      chartState.previewDate = null;
      if (dateInput) dateInput.value = chartState.pinnedDate || '';
      updateActiveState();
      ensureActiveDateVisible(chartState.pinnedDate);
    });

    root.onkeydown = (event) => {
      const currentIndex = Math.max(0, allDates.indexOf(chartState.pinnedDate));
      let nextIndex = currentIndex;
      if (event.key === 'ArrowLeft') nextIndex = Math.max(0, currentIndex - 1);
      else if (event.key === 'ArrowRight') nextIndex = Math.min(allDates.length - 1, currentIndex + 1);
      else if (event.key === 'Home') nextIndex = 0;
      else if (event.key === 'End') nextIndex = allDates.length - 1;
      else if (event.key === 'Escape') {
        chartState.previewDate = null;
        chartState.previewSeriesKey = null;
        updateActiveState();
        return;
      } else return;
      event.preventDefault();
      chartState.pinnedDate = allDates[nextIndex];
      chartState.previewDate = null;
      if (dateInput) dateInput.value = chartState.pinnedDate || '';
      updateActiveState();
      ensureActiveDateVisible(chartState.pinnedDate);
    };

    updateActiveState();
    ensureActiveDateVisible(chartState.pinnedDate);

    function ensureActiveDateVisible(date) {
      if (!date || root.scrollWidth <= root.clientWidth) return;
      const renderedWidth = svg.getBoundingClientRect().width || width;
      const targetX = (xFor(date) / width) * renderedWidth;
      const padding = 48;
      if (targetX >= root.scrollLeft + padding && targetX <= root.scrollLeft + root.clientWidth - padding) return;
      root.scrollLeft = Math.max(0, Math.min(root.scrollWidth - root.clientWidth, targetX - root.clientWidth / 2));
    }
  }

  function nearestChartDate(dates, requestedDate) {
    if (!dates.length) return null;
    if (!requestedDate) return dates.at(-1);
    if (dates.includes(requestedDate)) return requestedDate;
    const target = Date.parse(requestedDate);
    if (!Number.isFinite(target)) return dates.at(-1);
    return dates.reduce((nearest, date) => {
      const distance = Math.abs(Date.parse(date) - target);
      const nearestDistance = Math.abs(Date.parse(nearest) - target);
      return distance < nearestDistance ? date : nearest;
    }, dates[0]);
  }

  function chartPointAtDate(points, date) {
    if (!points.length || !date) return null;
    const exact = points.find((point) => point.date === date);
    if (exact) return exact;
    const previous = points.filter((point) => String(point.date) <= String(date)).at(-1);
    return previous || points[0] || null;
  }

  function renderComparisonValueCards(seriesList, date, activeSeriesKey) {
    const root = q('#comparison-value-grid');
    if (!root) return;
    root.replaceChildren(...seriesList.map((series) => {
      const point = chartPointAtDate(series.points, date);
      const article = el('article', `chart-value-card ${series.key}${series.key === activeSeriesKey ? ' is-active' : ''}`);
      article.append(
        span(shortSeriesLabel(series)),
        strong(point ? fmtPct(Number(point.equity) - 1) : '관측 없음'),
        small(`${series.sourceName || series.label} · ${point?.date || date || '—'}`)
      );
      return article;
    }));
  }

  function renderComparisonMetrics(payload, root, seriesList) {
    root.replaceChildren();
    const heading = el('div', 'performance-metrics-heading');
    const titleBox = document.createElement('div');
    const title = document.createElement('h4');
    title.textContent = '기간별 성과 지표 비교';
    const note = document.createElement('p');
    note.textContent = '기간별 누적 수익률, 위험조정 지표, MDD를 비교합니다.';
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
    setText(
      '#ranking-list-meta',
      `배지는 공식 종합점수 순위 · 화면 정렬 ${metricLabel(state.sortMetric)} · ${allVisible.length}개 검색${selectedExtraCount ? ` · 비교 1개 포함` : ''}`
    );
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
        span(`공식 #${row.rank ?? '—'}`, 'rank-badge'),
        strong(row.factor),
        span(`화면 기준 ${metricLabel(state.sortMetric)} ${fmtMetric(row[state.sortMetric], state.sortMetric)}`)
      );
      article.append(head, bar(percentForMetric(row[state.sortMetric], state.sortMetric), `정렬 지표 ${state.sortMetric}`));
      if (meta) {
        const detail = el('div', 'rank-detail');
        const method = factorMethodDetails(meta);
        detail.append(
          span(`${familyTitle(meta.category)} · ${fmtText(meta.kind)}`, 'badge'),
          small(meta.description),
          small(`산식: ${method.formula}`),
          small(`해석: ${method.method}`)
        );
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
      const automatic = selectedComparisonFactor(payload, String((payload.summary || {}).best_factor || ''));
      chips.replaceChildren(small(`차트 비교: 자동${automatic ? ` · ${automatic}` : ''}`));
      return;
    }
    const bestFactor = String((payload.summary || {}).best_factor || '');
    const chartComparison = selectedComparisonFactor(payload, bestFactor);
    chips.replaceChildren(...Array.from(state.selectedFactors).slice(0, 1).map((name) => {
      const chip = el('span', 'selected-chip');
      if (name === chartComparison) chip.classList.add('is-chart-comparison');
      chip.append(span(name), small('차트 비교 적용'));
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
      ['provider_order', metadata.provider_order || 'unknown'],
      ['provider_attempted_sources', metadata.provider_attempted_sources || 'unknown'],
      ['provider_fill_counts', metadata.provider_fill_counts || 'unknown'],
      ['provider_failed_tickers_by_source', metadata.provider_failed_tickers_by_source || 'unknown'],
      ['provider_error_count', metadata.provider_error_count ?? 'unknown'],
      ['provider_limitations', metadata.provider_limitations || 'unknown'],
      ['fallback_source', metadata.fallback_source || 'none'],
      ['fallback_filled_ticker_count', metadata.fallback_filled_ticker_count ?? 0],
      ['fallback_filled_tickers', metadata.fallback_filled_tickers || []],
      ['fetched_at', summary.fetched_at || metadata.fetched_at || 'missing'],
      ['price_adjustment', metadata.price_adjustment || 'unknown'],
      ['price_download_chunk_size', metadata.price_download_chunk_size || 'unknown'],
      ['price_download_chunk_count', metadata.price_download_chunk_count ?? 'unknown'],
      ['price_download_request_count', metadata.price_download_request_count ?? 'unknown'],
      ['price_download_yfinance_chunk_count', metadata.price_download_yfinance_chunk_count ?? 'unknown'],
      ['price_download_yahoo_chart_request_count', metadata.price_download_yahoo_chart_request_count ?? 'unknown'],
      ['price_download_success_rate', fmtPct(metadata.price_download_success_rate)],
      ['source_hash', summary.source_hash || metadata.source_hash || 'missing'],
      ['source_kind', metadata.source_kind || 'unknown'],
      ['data_end_date', summary.data_end_date || metadata.data_end_date || 'unknown'],
      ['universe_name', metadata.universe_name || 'unknown'],
      ['universe_ticker_count', metadata.universe_ticker_count || 'unknown'],
      ['requested_ticker_count', metadata.requested_ticker_count || 'unknown'],
      ['price_ticker_count', metadata.price_ticker_count || 'unknown'],
      ['rankable_stock_universe_count', metadata.rankable_stock_universe_count || 'unknown'],
      ['active_priced_stock_count', metadata.active_priced_stock_count || 'unknown'],
      ['history_qualified_ticker_count', metadata.history_qualified_ticker_count || 'unknown'],
      ['liquidity_qualified_ticker_count', metadata.liquidity_qualified_ticker_count || 'unknown'],
      ['latest_factor_eligible_ticker_count', metadata.latest_factor_eligible_ticker_count || 'unknown'],
      ['min_factor_eligible_tickers', metadata.min_factor_eligible_tickers || 'none'],
      ['min_history_observations', metadata.min_history_observations || 'none'],
      ['eligibility_adv_window', metadata.eligibility_adv_window || 'unknown'],
      ['eligibility_min_dollar_volume', metadata.eligibility_min_dollar_volume ?? 'unknown'],
      ['factor_eligibility_signal_date', metadata.factor_eligibility_signal_date || 'unknown'],
      ['rebalance_eligible_min_count', metadata.rebalance_eligible_min_count ?? 'unknown'],
      ['rebalance_eligible_median_count', metadata.rebalance_eligible_median_count ?? 'unknown'],
      ['rebalance_eligible_latest_count', metadata.rebalance_eligible_latest_count ?? 'unknown'],
      ['rebalance_history_qualified_latest_count', metadata.rebalance_history_qualified_latest_count ?? 'unknown'],
      ['rebalance_liquidity_qualified_latest_count', metadata.rebalance_liquidity_qualified_latest_count ?? 'unknown'],
      ['factor_eligibility_note', metadata.factor_eligibility_note || 'unknown'],
      ['min_price_tickers', metadata.min_price_tickers || 'none'],
      ['min_price_coverage_ratio', fmtPct(metadata.min_price_coverage_ratio)],
      ['min_latest_data_coverage_ratio', fmtPct(metadata.min_latest_data_coverage_ratio)],
      ['price_coverage_ratio', fmtPct(metadata.price_coverage_ratio)],
      ['latest_data_ticker_count', metadata.latest_data_ticker_count || 'unknown'],
      ['latest_data_coverage_ratio', fmtPct(metadata.latest_data_coverage_ratio)],
      ['latest_data_reference_date', metadata.latest_data_reference_date || 'unknown'],
      ['latest_data_max_date', metadata.latest_data_max_date || 'unknown'],
      ['latest_data_max_date_ticker_count', metadata.latest_data_max_date_ticker_count ?? 'unknown'],
      ['latest_data_reference_note', metadata.latest_data_reference_note || 'unknown'],
      ['universe_build_source_urls', metadata.universe_build_universe_source_urls || 'unknown'],
      ['universe_build_common_stock_candidate_count', metadata.universe_build_common_stock_candidate_count || 'unknown'],
      ['universe_build_excluded_symbol_counts', metadata.universe_build_excluded_symbol_counts || 'unknown'],
      ['factor_scores_archive', metadata.factor_scores_archive || 'unknown'],
      ['universe_scope_note', metadata.universe_scope_note || 'unknown'],
      ['universe_is_point_in_time', metadata.universe_is_point_in_time ?? 'unknown'],
      ['market_cap_filter_basis', metadata.market_cap_filter_basis || 'unknown'],
      ['market_cap_filter_attempted', metadata.market_cap_filter_attempted ?? 'unknown'],
      ['market_cap_filter_effective', metadata.market_cap_filter_effective ?? 'unknown'],
      ['market_cap_filter_status', metadata.market_cap_filter_status || 'unknown'],
      ['filter_fallback_reason', metadata.filter_fallback_reason || 'none'],
      ['current_screen_note', metadata.current_screen_note || 'unknown'],
      ['coverage_denominator', metadata.coverage_denominator || 'unknown'],
      ['transaction_cost_bps', metadata.transaction_cost_bps ?? 'unknown'],
      ['transaction_cost_model', metadata.transaction_cost_model || 'unknown'],
      ['transaction_cost_note', metadata.transaction_cost_note || 'unknown'],
      ['latest_portfolio_holding_count', metadata.latest_portfolio_holding_count ?? 'unknown'],
      ['latest_portfolio_effective_holdings', fmtNumber(metadata.latest_portfolio_effective_holdings, 2)],
      ['latest_portfolio_max_weight', fmtPct(metadata.latest_portfolio_max_weight)],
      ['latest_portfolio_top5_weight', fmtPct(metadata.latest_portfolio_top5_weight)],
      ['latest_portfolio_min_adv', fmtUsd(metadata.latest_portfolio_min_adv)],
      ['latest_portfolio_weighted_adv', fmtUsd(metadata.latest_portfolio_weighted_adv)],
      ['latest_portfolio_capacity_5pct_adv', fmtUsd(metadata.latest_portfolio_capacity_5pct_adv)],
      ['latest_portfolio_capacity_10pct_adv', fmtUsd(metadata.latest_portfolio_capacity_10pct_adv)],
      ['latest_portfolio_capacity_limit_ticker', metadata.latest_portfolio_capacity_limit_ticker || 'unknown'],
      ['latest_portfolio_average_turnover', fmtPct(metadata.latest_portfolio_average_turnover)],
      ['latest_portfolio_latest_turnover', fmtPct(metadata.latest_portfolio_latest_turnover)],
      ['latest_portfolio_capacity_note', metadata.latest_portfolio_capacity_note || 'unknown'],
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


  function factorMethodDetails(meta) {
    const kind = String(meta?.kind || 'unknown');
    const params = meta?.params || {};
    const dependencies = Array.isArray(meta?.dependencies) ? meta.dependencies : [];
    const lookback = Number(params.lookback);
    const skip = Number(params.skip || 0);
    const window = Number(params.window);
    const short = Number(params.short);
    const long = Number(params.long);
    const volWindow = Number(params.vol_window);
    const field = params.field ? String(params.field) : '';
    const direction = String(params.direction || 'positive');
    let formula = '카탈로그 정의에 따른 점수';
    let method = '같은 기준일의 종목별 점수를 계산한 뒤 값이 높은 순서로 팩터 랭킹과 편입 후보를 정렬합니다.';

    if (kind === 'momentum') {
      formula = Number.isFinite(lookback)
        ? `P(t-${skip}d) / P(t-${lookback}d) - 1${skip ? ` · 최근 ${skip}거래일 스킵` : ''}`
        : '조정종가 누적수익률';
      method = '조정종가 기준 누적수익률이 높을수록 강한 가격 모멘텀으로 봅니다.';
    } else if (kind === 'reversal') {
      formula = Number.isFinite(lookback) ? `-(P(t) / P(t-${lookback}d) - 1)` : '-최근 수익률';
      method = '최근 많이 오른 종목을 낮게, 되돌림 가능성이 큰 종목을 높게 보는 단기 반전 신호입니다.';
    } else if (kind === 'volatility') {
      const measure = params.measure ? String(params.measure) : 'total';
      formula = measure === 'range'
        ? `-mean((high-low)/close, ${windowLabel(window)})`
        : `-stdev(daily_return, ${windowLabel(window)})`;
      method = '값이 덜 음수일수록 변동성/일중 범위가 낮아 방어적 성격이 강합니다.';
    } else if (kind === 'return_skew') {
      formula = `skewness(daily_return, ${windowLabel(window)})`;
      method = '수익률 분포의 우측 비대칭이 클수록 긍정적으로 평가합니다.';
    } else if (kind === 'return_kurtosis') {
      formula = `-excess_kurtosis(daily_return, ${windowLabel(window)})`;
      method = '극단 꼬리가 큰 분포를 낮게 보고, 과도한 첨도를 방어적으로 벌점화합니다.';
    } else if (kind === 'tail_loss') {
      formula = `mean(worst 10% daily_return, ${windowLabel(window)})`;
      method = '최악 구간 평균 손실이 덜 나쁜 종목을 꼬리위험이 낮은 후보로 봅니다.';
    } else if (kind === 'trend_efficiency') {
      formula = `(P(t)/P(t-${window}d)-1) / sum(abs(daily_return), ${windowLabel(window)})`;
      method = '같은 수익률이라도 덜 지그재그로 이동한 추세를 높게 봅니다.';
    } else if (kind === 'return_consistency') {
      formula = `count(daily_return > 0) / ${windowLabel(window)}`;
      method = '상승일 비율이 높은 종목을 더 일관된 추세로 평가합니다.';
    } else if (kind === 'risk_adjusted_momentum') {
      formula = `momentum(${windowLabel(lookback)}, skip ${skip}d) / stdev(daily_return, ${windowLabel(volWindow)})`;
      method = '수익률을 변동성으로 나눠 같은 위험 대비 더 강한 모멘텀을 높게 봅니다.';
    } else if (kind === 'liquidity') {
      formula = `mean(volume × close, ${windowLabel(window)})`;
      method = '최근 평균 달러 거래대금이 클수록 유동성이 높다고 봅니다.';
    } else if (kind === 'illiquidity') {
      formula = `-mean(abs(daily_return)/(volume×close), ${windowLabel(window)}) × 1,000,000`;
      method = '같은 거래대금 대비 가격 충격이 작을수록 높은 점수를 줍니다.';
    } else if (kind === 'volume_trend') {
      formula = `mean($volume, ${windowLabel(short)}) / mean($volume, ${windowLabel(long)}) - 1`;
      method = '단기 거래대금이 장기 평균보다 증가한 정도를 봅니다.';
    } else if (kind === 'volume_shock') {
      formula = `(mean($volume, ${windowLabel(short)}) - baseline_mean) / baseline_stdev`;
      method = '최근 거래대금이 과거 기준선 대비 얼마나 이례적으로 커졌는지 봅니다.';
    } else if (kind === 'price_volume_corr') {
      formula = `corr(daily_return, Δ(volume×close), ${windowLabel(window)})`;
      method = '가격 상승과 거래대금 증가가 함께 나타나는 축적 압력을 봅니다.';
    } else if (kind === 'moving_average_gap') {
      formula = `P(t) / MA_${window} - 1`;
      method = '현재 가격이 이동평균보다 얼마나 위에 있는지로 추세 위치를 평가합니다.';
    } else if (kind === 'moving_average_cross') {
      formula = `MA_${short} / MA_${long} - 1`;
      method = '단기 이동평균이 장기 이동평균보다 강한 정도를 봅니다.';
    } else if (kind === 'range_position') {
      formula = `(close - low_${window}) / (high_${window} - low_${window})`;
      method = '최근 거래범위 안에서 현재가가 상단에 가까울수록 높은 점수입니다.';
    } else if (kind === 'drawdown_high') {
      formula = `P(t) / rolling_high_${window} - 1`;
      method = '최근 고점 대비 낙폭이 작을수록 추세 훼손이 적다고 봅니다.';
    } else if (kind === 'breakout_strength') {
      formula = `close / prior_high_${window} - 1`;
      method = '직전 고점을 얼마나 돌파했는지 또는 근접했는지 평가합니다.';
    } else if (kind === 'range_contraction') {
      formula = `-(avg_range_${short} / avg_range_${long} - 1)`;
      method = '단기 변동 범위가 장기 대비 축소된 안정 구간을 높게 봅니다.';
    } else if (kind === 'overnight_return') {
      formula = `mean(open(t) / close(t-1) - 1, ${windowLabel(window)})`;
      method = '장마감 후 다음 시가까지의 오버나잇 수익률 경향을 봅니다.';
    } else if (kind === 'intraday_return') {
      formula = `mean(close / open - 1, ${windowLabel(window)})`;
      method = '장중 시가 대비 종가 수익률 경향을 봅니다.';
    } else if (kind === 'acceleration') {
      formula = `momentum(${windowLabel(short)}, skip ${skip}d) - momentum(${windowLabel(long)}, skip ${skip}d)`;
      method = '짧은 기간 모멘텀이 긴 기간 모멘텀보다 개선된 속도를 봅니다.';
    } else if (kind === 'fundamental') {
      formula = direction === 'negative' ? `-${field}` : field;
      method = direction === 'negative' ? '낮을수록 좋은 재무 배수를 부호 반전해 점수화합니다.' : '높을수록 좋은 PIT 재무 지표를 점수로 사용합니다.';
    } else if (kind === 'composite') {
      formula = dependencies.length ? `average_rank(${dependencies.join(', ')})` : 'eligible base factor rank blend';
      method = '여러 기초 팩터의 순위를 평균해 한쪽 스타일 쏠림을 낮춘 복합 점수입니다.';
    }

    return { formula, method, params: paramsText(params, dependencies) };
  }

  function windowLabel(days) {
    const numeric = Number(days);
    if (!Number.isFinite(numeric) || numeric <= 0) return '정의 구간';
    const months = Math.round(numeric / 21);
    if (months >= 1 && Math.abs(months * 21 - numeric) <= 3) return `${numeric}거래일(약 ${months}개월)`;
    return `${numeric}거래일`;
  }

  function paramsText(params, dependencies = []) {
    const entries = Object.entries(params || {}).map(([key, value]) => `${key}=${value}`);
    if (dependencies.length) entries.push(`dependencies=${dependencies.join('+')}`);
    return entries.length ? entries.join(', ') : '별도 파라미터 없음';
  }

  function portfolioDiagnostics(payload) {
    const metadata = payload.metadata || {};
    return {
      holdingCount: Number(metadata.latest_portfolio_holding_count),
      weightSum: Number(metadata.latest_portfolio_weight_sum),
      minWeight: Number(metadata.latest_portfolio_min_weight),
      maxWeight: Number(metadata.latest_portfolio_max_weight),
      top5Weight: Number(metadata.latest_portfolio_top5_weight),
      effectiveHoldings: Number(metadata.latest_portfolio_effective_holdings),
      advWindow: metadata.latest_portfolio_adv_window,
      minAdv: Number(metadata.latest_portfolio_min_adv),
      minAdvTicker: metadata.latest_portfolio_min_adv_ticker,
      weightedAdv: Number(metadata.latest_portfolio_weighted_adv),
      capacity5: Number(metadata.latest_portfolio_capacity_5pct_adv),
      capacity10: Number(metadata.latest_portfolio_capacity_10pct_adv),
      capacityLimitTicker: metadata.latest_portfolio_capacity_limit_ticker,
      averageTurnover: Number(metadata.latest_portfolio_average_turnover),
      latestTurnover: Number(metadata.latest_portfolio_latest_turnover),
    };
  }

  function addSelectedFactor(factorName) {
    const name = String(factorName || '').trim();
    if (!name) return;
    state.selectedFactors.clear();
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
    if (!automation.primary_refresh_kst || automation.primary_refresh_kst === 'manual') {
      return '자동 스케줄 없음 · workflow_dispatch 수동 실행';
    }
    const fallback = automation.fallback_refresh_kst.length ? ` · fallback ${automation.fallback_refresh_kst.join(', ')}` : '';
    return `자동 ${automation.primary_refresh_kst}${fallback}`;
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

  function barRow({ label, value, width, negative, best, selected = false }) {
    const classNames = ['bar-row'];
    if (best) classNames.push('is-best');
    if (selected) classNames.push('is-selected');
    const row = el('div', classNames.join(' '));
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

  function fmtUsd(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '—';
    try {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        notation: 'compact',
        maximumFractionDigits: numeric >= 1000000 ? 1 : 0,
      }).format(numeric);
    } catch (_) {
      return `$${numeric.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
    }
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
      benchmarkLabelForTest: benchmarkLabel,
      portfolioDiagnosticsForTest: portfolioDiagnostics,
      fmtUsdForTest: fmtUsd,
      nearestChartDateForTest: nearestChartDate,
      chartPointAtDateForTest: chartPointAtDate,
      analysisConfigFromPayloadForTest: analysisConfigFromPayload,
      normalizeAnalysisConfigForTest: normalizeAnalysisConfig,
      buildAnalysisWorkflowCommandForTest: buildAnalysisWorkflowCommand,
      validateResultBindingForTest: validateResultBinding,
      marketCapDisplayForTest: marketCapDisplay,
      bindingStatusTextForTest: bindingStatusText,
    };
  }
})();
