import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const html = readFileSync(new URL('../docs/index.html', import.meta.url), 'utf8');
const app = readFileSync(new URL('../docs/app.js', import.meta.url), 'utf8');
const workflow = readFileSync(new URL('../.github/workflows/update-dashboard.yml', import.meta.url), 'utf8');

const INPUTS = {
  period: '5y',
  rebalance: 'M',
  top_n: 20,
  weighting: 'score',
  factor_preset: 'zoo',
  factor_allowlist: '',
  min_market_cap: 10_000_000_000,
  min_dollar_volume: 50_000_000,
  eligibility_adv_window: 63,
  transaction_cost_bps: 5,
  transaction_cost_model: 'one_way_notional',
};

function dashboardHelpers(overrides = {}) {
  const crypto = {
    randomUUID() {
      return '12345678-1234-4234-8234-123456789abc';
    },
    subtle: webcrypto.subtle,
  };
  const context = {
    console,
    URL,
    TextDecoder,
    TextEncoder,
    crypto,
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
    ...overrides,
  };
  context.globalThis = context;
  vm.createContext(context);
  vm.runInContext(app, context);
  return context.__bestFactorDashboard;
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function runEnvelope(overrides = {}) {
  const canonicalInputs = {
    ...INPUTS,
    factor_allowlist: [],
  };
  return {
    runId: 'bf-20260724-0001',
    projectId: 'best-factor',
    inputSchemaVersion: 'best-factor/v1',
    inputSchemaHash: 'd'.repeat(64),
    configHashAlgorithm: 'best-factor-python-json-v1',
    configHash: 'a'.repeat(64),
    effectiveConfigHash: 'a'.repeat(64),
    status: 'queued',
    createdAt: '2026-07-24T01:00:00Z',
    requestedInputs: { ...canonicalInputs },
    normalizedInputs: { ...canonicalInputs },
    effectiveInputs: { ...canonicalInputs },
    ignoredInputs: [],
    fallbacks: [],
    fallbackUsed: false,
    fallbackReason: null,
    ...overrides,
  };
}

test('API execution stays opt-in and keeps the static command fallback honest', () => {
  assert.match(html, /<meta name="quant-run-api-base" content=""\s*\/>/);
  assert.match(html, /id="analysis-settings"[^>]*>/);
  assert.doesNotMatch(html, /id="analysis-settings"[^>]*\sopen(?:\s|>)/);
  assert.match(html, /id="analysis-api-token"[\s\S]*?autocomplete="off"/);
  assert.match(html, /id="request-analysis-run"[^>]*\sdisabled/);
  assert.match(html, /대체 실행 경로/);
  assert.doesNotMatch(html + app, /API를 사용하지 않을 때 검토 후 실행할 수 있는 명령입니다/);
  assert.match(app, /allowFallback:\s*false/);
  assert.match(app, /Authorization:\s*`Bearer \$\{connection\.token\}`/);
  assert.match(app, /'Idempotency-Key': idempotencyKey/);
  assert.match(app, /`\/v1\/projects\/\$\{RUN_API_PROJECT_ID\}\/runs`/);
  assert.match(app, /`\/v1\/runs\/\$\{encodeURIComponent\(current\.runId\)\}`/);
  assert.match(app, /`\/v1\/runs\/\$\{encodeURIComponent\(current\.runId\)\}\/result`/);
  assert.match(app, /if \(current\.status === 'published'\)/);
  assert.match(app, /RUN_ARTIFACT_CONTRACT_VERSION = 'best-factor\/latest-results\/v1'/);
  assert.match(app, /bytes\.byteLength !== resultEnvelope\.artifact\.byteSize/);
  assert.match(app, /sourceHash !== resultEnvelope\.dataIdentity\.sourceHash/);
  assert.doesNotMatch(app, /localStorage[^;]*(?:token|bearer)|sessionStorage[^;]*(?:token|bearer)/i);
  const requestFunction = app.split('  async function requestAnalysisRun() {', 2)[1]
    .split('  function adoptVerifiedRun(', 1)[0];
  assert.doesNotMatch(requestFunction, /copyAnalysisWorkflowCommand|WORKFLOW_COMMAND|workflow_dispatch/);
  assert.equal(
    dashboardHelpers().createRunIdempotencyKeyForTest(),
    'best-factor-12345678-1234-4234-8234-123456789abc',
  );
});

test('run request maps exactly all 11 analysis inputs and excludes display-only state', () => {
  const helpers = dashboardHelpers();
  const request = plain(helpers.buildRunRequestForTest({
    ...INPUTS,
    factor_allowlist: 'momentum_6m,low_volatility',
    sortMetric: 'sharpe',
    display_top_n: 3,
  }));
  assert.deepEqual(request, {
    inputSchemaVersion: 'best-factor/v1',
    inputs: {
      period: '5y',
      rebalance: 'M',
      top_n: 20,
      weighting: 'score',
      factor_preset: 'zoo',
      factor_allowlist: ['momentum_6m', 'low_volatility'],
      min_market_cap: 10_000_000_000,
      min_dollar_volume: 50_000_000,
      eligibility_adv_window: 63,
      transaction_cost_bps: 5,
      transaction_cost_model: 'one_way_notional',
    },
    allowFallback: false,
  });
  assert.equal(Object.keys(request.inputs).length, 11);
  assert.equal('sortMetric' in request.inputs, false);
  assert.equal('display_top_n' in request.inputs, false);
  assert.equal('configHash' in request, false);
  assert.match(app, /const preserveDraft = Boolean\(draftInputs && !runInputsMatch\(draftInputs, result\.effectiveInputs\)\)/);
  assert.match(app, /draftPreserved:\s*preserveDraft/);
});

test('API base configuration is HTTPS-only outside localhost and cannot embed credentials', () => {
  const helpers = dashboardHelpers();
  assert.equal(helpers.normalizeRunApiBaseForTest('https://api.example.com/'), 'https://api.example.com');
  assert.equal(helpers.normalizeRunApiBaseForTest('http://127.0.0.1:8000/'), 'http://127.0.0.1:8000');
  assert.throws(() => helpers.normalizeRunApiBaseForTest('http://api.example.com'), /HTTPS/);
  assert.throws(() => helpers.normalizeRunApiBaseForTest('https://token@example.com'), /인증정보/);
  assert.throws(() => helpers.normalizeRunApiBaseForTest('https://api.example.com?token=x'), /쿼리/);
  assert.match(app, /credentials:\s*'omit'/);
  assert.match(app, /referrerPolicy:\s*'no-referrer'/);
});

test('polling covers the 90-minute worker budget and validates every status transition monotonically', () => {
  const intervalMatch = app.match(/RUN_API_POLL_INTERVAL_MS = ([\d_]+);/);
  const pollsMatch = app.match(/RUN_API_MAX_POLLS = ([\d_]+);/);
  assert.ok(intervalMatch);
  assert.ok(pollsMatch);
  const interval = Number(intervalMatch[1].replaceAll('_', ''));
  const polls = Number(pollsMatch[1].replaceAll('_', ''));
  assert.ok(interval * polls >= 90 * 60 * 1_000);
  assert.ok(interval * polls <= 3 * 60 * 60 * 1_000);
  assert.match(app, /current = normalizeRunEnvelope\(statusRaw, current\);/);
  assert.doesNotMatch(app, /current = normalizeRunEnvelope\(statusRaw, created\);/);
});

test('queued, dispatched, running, validating, failed, and stale states keep concise status copy', () => {
  const helpers = dashboardHelpers();
  const queued = helpers.normalizeRunEnvelopeForTest(runEnvelope(), { inputs: runEnvelope().requestedInputs });
  const dispatched = helpers.normalizeRunEnvelopeForTest(runEnvelope({ status: 'dispatched' }), queued);
  const running = helpers.normalizeRunEnvelopeForTest(runEnvelope({ status: 'running' }), queued);
  const validating = helpers.normalizeRunEnvelopeForTest(runEnvelope({ status: 'validating' }), queued);
  const failed = helpers.normalizeRunEnvelopeForTest(runEnvelope({ status: 'failed', errorMessage: 'worker error' }), queued);
  const stale = { ...plain(failed), status: 'stale', error: 'stale artifact' };
  assert.equal(queued.status, 'queued');
  assert.equal(dispatched.status, 'dispatched');
  assert.equal(running.status, 'running');
  assert.equal(validating.status, 'validating');
  assert.equal(failed.status, 'failed');
  assert.equal(failed.error, 'worker error');
  assert.equal(stale.status, 'stale');
  assert.match(helpers.runStatusMessageForTest(queued), /대기 중/);
  assert.match(helpers.runStatusMessageForTest(dispatched), /작업 전달/);
  assert.match(helpers.runStatusMessageForTest(running), /분석 중/);
  assert.match(helpers.runStatusMessageForTest(validating), /결과 검증 중/);
  assert.match(helpers.runStatusMessageForTest(failed), /실행 실패/);
  assert.match(helpers.runStatusMessageForTest(stale), /오래된 결과 · 미적용/);
  for (const envelope of [queued, dispatched, running, validating, failed, stale]) {
    assert.doesNotMatch(helpers.runStatusMessageForTest(envelope), /현재 정적 결과|artifact binding/);
  }
  assert.equal(helpers.runStatusLabelForTest('queued'), '대기');
  assert.equal(helpers.runStatusLabelForTest('dispatched'), '작업 전달');
  assert.equal(helpers.runStatusLabelForTest('running'), '분석 중');
  assert.equal(helpers.runStatusLabelForTest('validating'), '결과 검증 중');
  assert.equal(helpers.runStatusLabelForTest('failed'), '실패');
  assert.equal(helpers.runStatusLabelForTest('stale'), '오래된 결과');
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(runEnvelope({ status: 'queued' }), running),
    /이전 단계/,
  );
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(runEnvelope({ status: 'running' }), failed),
    /종료된 실행 상태/,
  );
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(runEnvelope({ status: 'succeeded' }), queued),
    /지원하지 않는 실행 상태/,
  );
});

test('status and result identity mismatches fail closed', () => {
  const helpers = dashboardHelpers();
  const created = helpers.normalizeRunEnvelopeForTest(runEnvelope(), { inputs: runEnvelope().requestedInputs });
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(runEnvelope({ status: 'running', configHash: 'b'.repeat(64) }), created),
    /configHash/,
  );
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(runEnvelope({ status: 'running', effectiveConfigHash: 'b'.repeat(64) }), created),
    /effectiveConfigHash/,
  );
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(runEnvelope({
      status: 'running',
      effectiveInputs: { ...runEnvelope().effectiveInputs, top_n: 19 },
    }), created),
    /effectiveInputs/,
  );
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(runEnvelope({ inputSchemaVersion: 'best-factor/v2' }), created),
    /inputSchemaVersion/,
  );
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(runEnvelope({ configHashAlgorithm: 'unknown' }), created),
    /configHashAlgorithm/,
  );
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(runEnvelope({ ignoredInputs: ['min_market_cap'] }), created),
    /fallback을 허용하지 않은/,
  );
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(runEnvelope({ fallbacks: [{ code: 'market_cap_metadata_insufficient' }] }), created),
    /fallback을 허용하지 않은/,
  );
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(runEnvelope({ fallbackUsed: true, fallbackReason: 'unexpected' }), created),
    /fallback 상태/,
  );
  const missingIgnoredInputs = runEnvelope();
  delete missingIgnoredInputs.ignoredInputs;
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest(missingIgnoredInputs, created),
    /ignoredInputs/,
  );
  const omittedOptionalFallbackReason = runEnvelope();
  delete omittedOptionalFallbackReason.fallbackReason;
  assert.equal(
    helpers.normalizeRunEnvelopeForTest(omittedOptionalFallbackReason, created).fallbackReason,
    null,
  );

  const result = runEnvelope({
    status: 'published',
    dataAsOf: '2026-07-23',
    calculatedAt: '2026-07-24T01:05:00Z',
    codeVersion: '0'.repeat(40),
    dataIdentity: {
      source: 'best-factor-live',
      sourceHash: 'a54e4adee3d58bc3',
      dataAsOf: '2026-07-23',
    },
    artifact: {
      url: `https://raw.githubusercontent.com/SonChangGi/best-factor/${'1'.repeat(40)}/docs/data/latest-results.json`,
      sha256: 'c'.repeat(64),
      byteSize: 2048,
      contractVersion: 'best-factor/latest-results/v1',
    },
    payload: {
      schema_version: 1,
      generated_at: '2026-07-24T01:05:00Z',
      summary: {
        data_end_date: '2026-07-23',
        source_hash: 'a54e4adee3d58bc3',
      },
    },
  });
  const published = helpers.normalizeRunEnvelopeForTest(result, created);
  assert.equal(helpers.normalizeRunResultEnvelopeForTest(result, published).artifact.sha256, 'c'.repeat(64));
  assert.throws(
    () => helpers.normalizeRunResultEnvelopeForTest({ ...result, runId: 'bf-20260724-9999' }, published),
    /실행 식별자/,
  );
  assert.throws(
    () => helpers.normalizeRunResultEnvelopeForTest({ ...result, calculatedAt: '2026-07-24T00:59:59Z' }, published),
    /calculatedAt/,
  );
  assert.throws(
    () => helpers.normalizeRunResultEnvelopeForTest({ ...result, artifact: { ...result.artifact, sha256: 'bad' } }, published),
    /SHA-256/,
  );
  assert.throws(
    () => helpers.normalizeRunResultEnvelopeForTest({
      ...result,
      dataIdentity: { ...result.dataIdentity, dataAsOf: '2026-07-22' },
    }, published),
    /dataAsOf/,
  );
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest({
      ...result,
      dataIdentity: { ...result.dataIdentity, sourceHash: 'not-a-hex-hash' },
    }, created),
    /sourceHash/,
  );
  assert.throws(
    () => helpers.normalizeRunResultEnvelopeForTest({
      ...result,
      artifact: { ...result.artifact, byteSize: 2049 },
    }, published),
    /artifact identity/,
  );
  const missingPayload = { ...result };
  delete missingPayload.payload;
  assert.throws(
    () => helpers.normalizeRunResultEnvelopeForTest(missingPayload, published),
    /result payload|결과 payload/,
  );
  assert.throws(
    () => helpers.normalizeRunEnvelopeForTest({ ...runEnvelope(), inputSchemaHash: 'bad' }, created),
    /inputSchemaHash/,
  );
});

test('artifact must match calculation time, data date, and be newer than the static fallback', () => {
  const helpers = dashboardHelpers();
  const binding = {
    calculatedAt: '2026-07-24T01:05:00Z',
    dataAsOf: '2026-07-23',
    dataIdentity: {
      source: 'best-factor-live',
      sourceHash: 'a54e4adee3d58bc3',
      dataAsOf: '2026-07-23',
    },
  };
  const artifact = {
    schema_version: 1,
    generated_at: '2026-07-24T01:05:00Z',
    summary: {
      data_end_date: '2026-07-23',
      source_hash: 'a54e4adee3d58bc3',
    },
  };
  assert.equal(
    helpers.validateAdoptableArtifactForTest(artifact, binding, { generated_at: '2026-07-24T01:00:00Z' }),
    true,
  );
  assert.throws(
    () => helpers.validateAdoptableArtifactForTest(
      artifact,
      binding,
      { generated_at: '2026-07-24T01:05:00Z' },
    ),
    /stale artifact/,
  );
  assert.throws(
    () => helpers.validateAdoptableArtifactForTest(
      { ...artifact, generated_at: '2026-07-24T01:04:59Z' },
      binding,
      { generated_at: '2026-07-24T01:00:00Z' },
    ),
    /생성 시각/,
  );
  assert.throws(
    () => helpers.validateAdoptableArtifactForTest(
      { ...artifact, summary: { data_end_date: '2026-07-22' } },
      binding,
      { generated_at: '2026-07-24T01:00:00Z' },
    ),
    /데이터 기준일/,
  );
  assert.throws(
    () => helpers.validateAdoptableArtifactForTest(
      { ...artifact, summary: { ...artifact.summary, source_hash: 'different' } },
      binding,
      { generated_at: '2026-07-24T01:00:00Z' },
    ),
    /source hash/,
  );
  assert.equal(
    helpers.validateAdoptableArtifactForTest(
      { ...artifact, summary: { ...artifact.summary, source_hash: 'A54E4ADEE3D58BC3' } },
      binding,
      { generated_at: '2026-07-24T01:00:00Z' },
    ),
    true,
  );
  assert.equal(
    helpers.jsonSemanticallyEqualForTest(
      { summary: { source_hash: 'abc12345', data_end_date: '2026-07-23' }, rows: [1, 2] },
      { rows: [1, 2], summary: { data_end_date: '2026-07-23', source_hash: 'abc12345' } },
    ),
    true,
  );
  assert.equal(
    helpers.jsonSemanticallyEqualForTest(
      { rows: [1, 2] },
      { rows: [2, 1] },
    ),
    false,
  );
  const bounded = plain(helpers.boundedControlResultPayloadForTest({
    ...artifact,
    rankings: [{ factor: 'must-not-enter-api-payload' }],
    summary: {
      ...artifact.summary,
      best_factor: 'quality_roe',
      unknown_large_field: 'must-not-enter-api-payload',
    },
  }));
  assert.deepEqual(bounded, {
    schema_version: 1,
    generated_at: '2026-07-24T01:05:00Z',
    summary: {
      best_factor: 'quality_roe',
      data_end_date: '2026-07-23',
      source_hash: 'a54e4adee3d58bc3',
    },
  });
  assert.throws(
    () => helpers.boundedControlResultPayloadForTest(
      { ...bounded, rankings: [] },
      true,
    ),
    /bounded summary/,
  );
  assert.match(app, /다운로드한 artifact 요약이 API result payload binding과 일치하지 않습니다/);
});

test('full artifact bytes, hash, identity, and bounded summary are verified before adoption', async () => {
  const fullArtifact = {
    schema_version: 1,
    generated_at: '2026-07-24T01:05:00Z',
    summary: {
      best_factor: 'quality_roe',
      data_end_date: '2026-07-23',
      source_hash: 'a54e4adee3d58bc3',
    },
    rankings: [{ factor: 'quality_roe', composite_score: 1.23 }],
  };
  let servedBytes = new TextEncoder().encode(JSON.stringify(fullArtifact));
  const digest = await webcrypto.subtle.digest('SHA-256', servedBytes);
  const sha256 = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
  let requestInit;
  const helpers = dashboardHelpers({
    fetch: async (_url, init) => {
      requestInit = init;
      const copy = servedBytes.slice();
      return {
        ok: true,
        status: 200,
        headers: { get: (name) => name.toLowerCase() === 'content-length' ? String(copy.byteLength) : null },
        arrayBuffer: async () => copy.buffer.slice(copy.byteOffset, copy.byteOffset + copy.byteLength),
      };
    },
  });
  const created = helpers.normalizeRunEnvelopeForTest(runEnvelope(), { inputs: runEnvelope().requestedInputs });
  const published = helpers.normalizeRunEnvelopeForTest(runEnvelope({
    status: 'published',
    dataAsOf: '2026-07-23',
    calculatedAt: '2026-07-24T01:05:00Z',
    codeVersion: '0'.repeat(40),
    dataIdentity: {
      source: 'best-factor-live',
      sourceHash: 'a54e4adee3d58bc3',
      dataAsOf: '2026-07-23',
    },
    artifact: {
      url: `https://raw.githubusercontent.com/SonChangGi/best-factor/${'1'.repeat(40)}/docs/data/latest-results.json`,
      sha256,
      byteSize: servedBytes.byteLength,
      contractVersion: 'best-factor/latest-results/v1',
    },
    payload: helpers.boundedControlResultPayloadForTest(fullArtifact),
  }), created);
  const result = helpers.normalizeRunResultEnvelopeForTest({
    ...published,
    payload: helpers.boundedControlResultPayloadForTest(fullArtifact),
  }, published);
  const verified = await helpers.fetchAndVerifyRunArtifactForTest(
    { baseUrl: 'https://raw.githubusercontent.com', token: 'tab-only-token' },
    result,
  );
  assert.deepEqual(plain(verified), fullArtifact);
  assert.deepEqual(plain(requestInit.headers), { Accept: 'application/json' });
  assert.equal(requestInit.credentials, 'omit');
  assert.equal(requestInit.referrerPolicy, 'no-referrer');

  servedBytes = new TextEncoder().encode(JSON.stringify({
    ...fullArtifact,
    rankings: [{ factor: 'tampered', composite_score: 9.99 }],
  }));
  await assert.rejects(
    helpers.fetchAndVerifyRunArtifactForTest(
      { baseUrl: 'https://raw.githubusercontent.com', token: 'tab-only-token' },
      result,
    ),
    /byteSize|SHA-256/,
  );
});

test('the API contract never changes the existing 11-input workflow mapping', () => {
  const dispatchBlock = workflow.split('    inputs:\n')[1].split('  schedule:\n')[0];
  const analyticalNames = [...dispatchBlock.matchAll(/^      ([a-z][a-z0-9_]*):$/gm)]
    .map((match) => match[1])
    .filter((name) => ![
      'allow_fallback',
      'control_run_id',
      'control_input_schema_version',
      'control_input_schema_hash',
      'control_config_hash_algorithm',
      'control_config_hash',
    ].includes(name));
  assert.deepEqual(analyticalNames, Object.keys(INPUTS));
  assert.match(dispatchBlock, /allow_fallback:[\s\S]*?default: false[\s\S]*?type: boolean/);
  assert.match(dispatchBlock, /control_run_id:[\s\S]*?default: ""[\s\S]*?type: string/);
  assert.match(dispatchBlock, /control_input_schema_version:[\s\S]*?default: ""[\s\S]*?type: string/);
  assert.match(dispatchBlock, /control_input_schema_hash:[\s\S]*?default: ""[\s\S]*?type: string/);
  assert.match(dispatchBlock, /control_config_hash_algorithm:[\s\S]*?default: ""[\s\S]*?type: string/);
  assert.match(dispatchBlock, /control_config_hash:[\s\S]*?default: ""[\s\S]*?type: string/);
  assert.match(workflow, /id: data_commit/);
  assert.match(workflow, /summary_allowlist = \(/);
  assert.match(workflow, /"payload": bounded_payload/);
  assert.match(workflow, /\/v1\/internal\/runs\/\$\{CONTROL_RUN_ID\}\/failure/);
  assert.match(
    workflow,
    /https:\/\/raw\.githubusercontent\.com\/SonChangGi\/best-factor\/\$\{DATA_COMMIT_SHA\}\/docs\/data\/latest-results\.json/,
  );
  assert.doesNotMatch(
    workflow.split('- name: Verify immutable control-run artifact', 2)[1],
    /DEPLOYED_PAGE_URL/,
  );
});
