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

The deployed `best-factor` page is refreshed by the `SonChangGi/best-factor` GitHub Actions workflow only. Live-data cron schedules are suspended after the multi-repo rollback. Pushes deploy the committed `docs/` artifact; reviewed `workflow_dispatch` runs execute the live-data path.

The live run uses `yfinance_yahoo_chart`: yfinance is attempted first, and tickers missing from that path are retried through a direct Yahoo chart JSON adapter. The dashboard's manual update button opens the same workflow dispatch page because a static GitHub Pages site cannot safely run Python or store a GitHub token in the browser.

The economic read-through panel is an explanatory layer over the generated metrics. It does not turn the exploratory factor-zoo winner into investment advice; it highlights economic rationale, risk-adjusted metrics, holdout robustness, concentration, and execution caveats.
