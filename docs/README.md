# Best Factor Lab static dashboard

This directory is a GitHub Pages-ready static site for `best-factor` outputs. The dashboard is designed for the factor-zoo default run, so the JSON should normally include 300+ tested candidate factors, public factor-family metadata, and explicit multiple-testing/free-data caveats. The ranking-card section shows Top 20 by default and lets readers add extra factors for comparison instead of rendering every candidate card at once.

Fast local smoke run with the compact preset:

```bash
python -m best_factor.cli run \
  --prices-file tests/fixtures/prices.csv \
  --universe-file tests/fixtures/universe.csv \
  --fundamentals-file tests/fixtures/fundamentals.csv \
  --output-dir runs/fixture-core \
  --rebalance M \
  --top-n 3 \
  --factor-preset core
```

Factor-zoo sample run for the checked-in dashboard JSON:

```bash
python -m best_factor.cli run \
  --prices-file tests/fixtures/prices.csv \
  --universe-file tests/fixtures/universe.csv \
  --fundamentals-file tests/fixtures/fundamentals.csv \
  --output-dir runs/fixture-zoo \
  --rebalance M \
  --top-n 3

python -m best_factor.cli site \
  --run-dir runs/fixture-zoo \
  --output-file docs/data/latest-results.json \
  --data-scope fixture_sample
```

Open locally:

```bash
python -m http.server --directory docs 8000
```

Open `http://127.0.0.1:8000/`. Opening `index.html` directly with `file://` may block JSON loading in some browsers, so serve the directory over HTTP or GitHub Pages.

Interpretation note: the displayed winner is the best factor among tested candidates in that run, not an out-of-sample-validated anomaly or investment recommendation.

## Update automation

The deployed `best-factor` page continues to work from committed static JSON and the `SonChangGi/best-factor` GitHub Actions workflow. The live-data path runs on a 07:00 KST Tue-Sat primary schedule after expected US regular sessions; 09:00/11:00/13:00 KST fallback schedules rerun only when the deployed JSON is stale, missing, or broken. Successful live runs commit the regenerated `docs/data/*.json` files before deploying Pages so later source pushes do not redeploy older committed data. Reviewed `workflow_dispatch` runs use the same validation, commit, and deploy path.

The analysis-input disclosure also supports an optional authenticated control API. It is disabled by default because `<meta name="quant-run-api-base">` is empty. A reviewer may enter an HTTPS API base and a short-lived bearer token for the current tab; the token is never written to local or session storage. The client posts the 11 inputs with an idempotency key to `POST /v1/projects/best-factor/runs`, polls `GET /v1/runs/{runId}` for up to two hours, and reads `GET /v1/runs/{runId}/result` only after `published`. It replaces the in-memory view only after the requested, normalized, and effective inputs, server `configHash`, matching `effectiveConfigHash`, `inputSchemaHash`, code version, `dataIdentity`, dates, artifact contract version, downloaded byte size, artifact SHA-256, and the full artifact's derived bounded summary all agree. Any API, stale-result, fallback, or binding failure leaves the committed static result visible. The command-copy path remains available and is never triggered automatically as an API fallback. Control-API workflow dispatches carry the API run/schema/config binding in separate operational inputs for exact correlation. After deployment, Actions verifies the commit-addressed immutable artifact byte-for-byte and sends a protected result-manifest callback; direct and scheduled runs skip that callback.

The live run uses `yfinance_yahoo_chart`: yfinance is attempted first, and tickers missing from that path are retried through a direct Yahoo chart JSON adapter. Manual workflow runs now fail closed when the configured market-cap screen lacks enough metadata. The separate `allow_fallback` operational input defaults to `false`; setting it to `true` explicitly permits the existing liquidity-only fallback. Scheduled refreshes retain that fallback policy and log it visibly.

The economic read-through panel is an explanatory layer over the generated metrics. It does not turn the exploratory factor-zoo winner into investment advice; it highlights economic rationale, risk-adjusted metrics, holdout robustness, concentration, and execution caveats.
