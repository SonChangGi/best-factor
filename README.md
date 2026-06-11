# best-factor

`best-factor` is a dependency-light Python CLI for researching which long-only US equity factor ranks highest among tested candidates in a given run under free-data constraints. It maps each tested factor to actual stock holdings and weights, backtests weekly or monthly rebalancing, ranks factors with return and downside metrics, and writes CSV, Markdown, and static HTML dashboard reports.

> Research only: this project does **not** provide investment advice or trade execution.

## What it does

- Loads a US stock universe and long-form OHLCV prices from CSV, or optionally fetches live prices through `yfinance`.
- Computes a factor-zoo-scale signal library that maps every tested factor to concrete tickers:
  - Default `--factor-preset zoo`: 300+ generated OHLCV/fundamental-optional candidates spanning momentum, reversal, volatility, upside/downside risk, return distribution, tail loss, risk-adjusted momentum, liquidity, Amihud-style illiquidity, volume shock/trend, price-volume confirmation, moving-average trend, range position, breakout, drawdown-to-high, trend efficiency/consistency, overnight/intraday returns, optional PIT value/quality/growth fields, and composite blends.
  - `--factor-preset core`: the legacy compact set (`momentum_12_1`, `momentum_6m`, `low_volatility`, `short_reversal`, `risk_adjusted_momentum`, `liquidity`, `value_pe`, `quality_roe`, `composite_defensive`) for fast smoke runs.
  - `--factors ...`: explicit allowlist that overrides the preset.
- Builds long-only top-N portfolios with equal or score weights.
- Supports monthly (`M`) and weekly (`W`) rebalancing.
- Applies optional market-cap and dollar-volume filters.
- Measures CAGR, annualized return, volatility, Sharpe, Sortino, Calmar, max drawdown, turnover, emitted-period coverage, and a deterministic composite score.
- Emits recent-tail holdout metrics/rankings as a secondary robustness check so the in-sample winner is not presented without a recency stress check.
- Emits current/latest holdings and weights for the best factor among the tested candidates.
- Writes a dependency-free `report.html` dashboard with summary cards, ranking bars, metric tables, holdings weights, diagnostics, metadata, and caveats.
- Exports the same run artifacts into a GitHub Pages-ready `docs/` dashboard similar to the reference static dashboard pattern.

## Install

No runtime dependency is required for CSV/offline runs:

```bash
python -m pip install -e .
```

Optional live Yahoo/yfinance support:

```bash
python -m pip install -e '.[live]'
```

## Quick offline smoke run

```bash
python -m best_factor.cli run \
  --prices-file tests/fixtures/prices.csv \
  --universe-file tests/fixtures/universe.csv \
  --fundamentals-file tests/fixtures/fundamentals.csv \
  --output-dir runs/fixture \
  --rebalance M \
  --top-n 3 \
  --factor-preset core
```

The default preset is `zoo`; use `--factor-preset core` when you want a fast compact run, or `--factors momentum_6m low_volatility` when you want an explicit allowlist.

Or after editable install:

```bash
best-factor run \
  --prices-file tests/fixtures/prices.csv \
  --universe-file tests/fixtures/universe.csv \
  --fundamentals-file tests/fixtures/fundamentals.csv \
  --output-dir runs/fixture \
  --rebalance M \
  --top-n 3
```

## Optional live free-data run

```bash
best-factor run \
  --provider yfinance \
  --tickers AAPL MSFT NVDA AMZN META GOOGL JPM XOM LLY AVGO \
  --period 5y \
  --output-dir runs/live-smoke \
  --rebalance M \
  --top-n 5 \
  --factor-preset zoo
```

The live path is intentionally optional because free public data can fail, be rate-limited, or change format.

## Output artifacts

Each run writes:

- `factor_metrics.csv`
- `factor_rankings.csv`
- `factor_holdout_metrics.csv`
- `factor_holdout_rankings.csv`
- `latest_holdings.csv`
- `portfolio_returns.csv`
- `factor_scores.csv`
- `skipped_reasons.csv`
- `prices_snapshot.csv`
- `universe_snapshot.csv`
- `run_config.json`
- `run_metadata.json`
- `report.md`
- `report.html`
- optional GitHub Pages JSON via `best-factor site`: `docs/data/latest-results.json`

The latest best-tested-factor holdings include `rebalance_date`, `factor`, `ticker`, `weight`, `score`, and `price_date_used`. Weights sum to approximately 1.0 for non-empty eligible portfolios. These are research portfolio weights under the close-to-close convention, not executable trade instructions. Holdout artifacts use each factor's most recent 25% of emitted return periods, with at least 6 periods when available, as a secondary robustness check; this is not a fully untouched out-of-sample experiment.

Open `report.html` in a browser to inspect the analysis visually. It is a static file with inline CSS only; no CDN, JavaScript, or remote chart dependency is required. Visual bars are clamped to `0-100%` and exact numeric metric values remain visible in text.

## GitHub Pages-style dashboard

The `docs/` directory contains a local-asset-only static dashboard for GitHub Pages. It reads `docs/data/latest-results.json`, renders Korean summary cards, factor-family explanations, Top 20 ranking cards plus user-selected comparison factors, latest holdings/weights, diagnostics, metadata, and free-data caveats, and shows an explicit static-data warning with `generated_at`, source hash, and run/fetch time when available.

Export a run into the site JSON schema:

```bash
python -m best_factor.cli site \
  --run-dir runs/fixture \
  --output-file docs/data/latest-results.json \
  --data-scope csv_run
```

Serve locally before opening the page, because some browsers block `fetch()` for `file://` pages:

```bash
python -m http.server --directory docs 8000
# open http://127.0.0.1:8000/
```

To publish manually, use the isolated `SonChangGi/best-factor` repository and its GitHub Pages custom workflow. Do not use another project repository or branch-source Pages target.

## Isolated GitHub Pages deployment

This project must be deployed only to its own repository. The intended public URL is:

- `https://sonchanggi.github.io/best-factor/`
- GitHub repository: `SonChangGi/best-factor`

It must not publish to, link to, trigger workflows in, or reuse assets from any other repository or Pages site. No other project is a deployment target for this repository.

The `docs/` dashboard includes an update panel. Because GitHub Pages is static, the button does not run compute anonymously in the browser and it does not embed a token. It opens the new repository's GitHub Actions workflow; a user with repository permission can run the workflow manually:

```bash
gh workflow run update-dashboard.yml --repo SonChangGi/best-factor --ref main
```

The workflow pins the live yfinance dependency, runs network-free tests plus syntax/static import checks before live generation, archives each generated run artifact, and uses GitHub Pages custom workflow deployment (`actions/configure-pages`, `actions/upload-pages-artifact`, and `actions/deploy-pages`) so the generated `docs/` artifact is published by that same run. It intentionally does not rely on a workflow self-commit to trigger a branch-based Pages build.

### KST daily update automation

The only automated deployment target is `SonChangGi/best-factor`. The workflow schedules are written in UTC but map to Korea Standard Time:

- `0 0 * * *` → **09:00 KST** primary daily refresh. It always regenerates the live yfinance run.
- `0 1 * * *` → **10:00 KST** fallback freshness check. It reruns only if the deployed `latest-results.json` is missing, broken, not generated today in KST, or has `data_end_date` older than the latest expected US regular trading session.
- `0 3 * * *` → **12:00 KST** second fallback check for provider/API delays.
- `0 6 * * *` → **15:00 KST** same-day stale-data retry for slower free-data availability.
- `0 9 * * *` → **18:00 KST** final same-day stale-data retry.

Fallback checks use the same stale/missing-data gate and skip if an earlier result is already current.

For manual and scheduled updates, the deployed Pages artifact is the freshness source of truth; the checked-in `docs/data/latest-results.json` is a seed/sample until the next workflow artifact is deployed. The freshness gate is implemented in `.github/scripts/check_dashboard_freshness.py` with a small NYSE holiday/weekend calendar so Korean-morning checks do not demand impossible weekend/holiday data.

### Live dashboard universe

`.github/best-factor-dashboard-tickers.txt` is the committed public dashboard universe. It is a curated list of individual large/liquid US stocks, not a survivorship-free historical universe and not the whole US market. The workflow builds best-effort current universe metadata from yfinance, applies a liquidity filter, and runs a market-cap-filtered backtest only after a metadata preflight confirms enough names meet the threshold. If the preflight is insufficient, it runs a liquidity-only fallback and records `market_cap_metadata_insufficient_preflight`; other CLI/provider failures are not swallowed by the fallback. The final run metadata records whether the market-cap filter was attempted, whether it was effective, and any fallback reason so two dashboard snapshots are not silently compared under different screens.

This keeps the public page reproducible and cheap to update, but the results remain research-grade and current-universe biased.

## Data schemas

Canonical output/internal schemas are enforced by tests:

- `prices`: `ticker`, `date`, `open`, `high`, `low`, `close`, `adj_close`, `volume`, `source`, `fetched_at`
- `universe`: `ticker`, `name`, `exchange`, `asset_type`, `active`, `market_cap`, `sector`, `source`, `as_of_date`
- `factor_scores`: `factor`, `ticker`, `signal_date`, `score`, `rank`, `eligible`, `skip_reason`
- `holdings`: `rebalance_date`, `factor`, `ticker`, `weight`, `score`, `price_date_used`
- `metrics/rankings`: `factor`, `cagr`, `annual_return`, `volatility`, `sharpe`, `sortino`, `calmar`, `max_drawdown`, `turnover`, `coverage`, `composite_score`

## Timing convention / no-lookahead rule

Research convention: signals at date `t` use closing data available through `t`; reported portfolio returns are close-to-close from `t` to the next rebalance close. This is useful for comparing factors but is **not** an intraday trade-execution model, and same-close portfolio formation can be optimistic versus executable next-session trading. Weekly schedules use the last available trading session in each ISO week. Monthly schedules use the last available trading session in each calendar month.

## Ranking formula

The default composite score is deterministic:

- Reward metrics: CAGR 20%, Sharpe 25%, Sortino 20%, Calmar 20%.
- Penalty metrics: absolute max drawdown 10%, volatility 5%.
- Metrics are min-max normalized across tested factors.
- Missing metrics receive the worst normalized score.
- Equal/single-factor metric ranges receive a deterministic 0.5 normalized score.
- Calmar is computed as CAGR divided by absolute max drawdown. Tie-break order: composite score desc, Sharpe desc, CAGR desc, max drawdown desc (less negative is better), factor name asc. Undefined or extreme positive Sortino/Calmar ratios from zero or near-zero downside are capped at 999 for deterministic, non-misleading reports.


## Factor-zoo presets, rank eligibility, and universe boundaries

The default run uses `--factor-preset zoo`, which expands to the full generated library. `--factor-preset core` keeps the compact legacy set for development speed, and `--factors` explicitly selects named factors and overrides the preset. The reported winner is the best among tested candidates in that run, not proof of a universal anomaly.

A factor must produce at least one non-empty portfolio period (`coverage > 0`) to appear in `factor_rankings.csv` or become the best factor. `coverage` is measured over emitted portfolio-return periods after missing-price and eligibility skips, not over every scheduled calendar rebalance. If filters leave no rank-eligible factor, the CLI exits with a controlled error instead of reporting a misleading all-empty winner. Universe rows are filtered to active stock/equity asset types by default.

`composite_defensive` depends on `momentum_6m`, `low_volatility`, and `liquidity`; all three dependencies must be eligible for a ticker before the composite row becomes eligible. When requested alone, those dependencies are computed internally but only the composite factor is emitted/ranked. Unknown factor names are rejected before a run starts.

## Free-data limitations

The default approach uses free/current-universe data and should be interpreted as research-grade, not institutional-grade:

- Current symbol lists are not survivorship-bias-free historical constituents.
- Yahoo/yfinance data can be delayed, revised, rate-limited, unavailable, or subject to Yahoo terms.
- Live yfinance and CSV price loaders scale `open`, `high`, `low`, and `close` to the `adj_close` basis before OHLC-derived factor scoring, preventing raw/adjusted price-scale mixing around dividends and splits.
- Current yfinance universe membership and market-cap metadata are current screens, not historical point-in-time constituent or point-in-time market-cap filters.
- Fundamental files must include `as_of_date` and `available_at`; rows without `available_at` are treated as non-point-in-time and skipped for historical factor scoring.
- Some factors or rows may be skipped with explicit reason codes such as `missing_fundamentals`, `insufficient_history`, `insufficient_volume`, `market_cap_unavailable`, `market_cap_below_min`, `empty_after_filters`, `provider_error`, `not_enough_assets`, `missing_rebalance_price`, `missing_exit_price`, `invalid_period_missing_price`, `inactive_or_non_stock`, and dynamic `zero_coverage:<factor>` diagnostics.
- Factor-zoo mode compares many related definitions. The top-ranked factor can be an in-sample winner caused by multiple-testing/data-snooping. The reported recent-tail holdout rank is a robustness diagnostic, not proof of a universal anomaly; recheck with true holdout periods, alternate universes, costs, and higher-quality point-in-time data before drawing investment conclusions.

For higher-confidence research, use a survivorship-aware universe and point-in-time fundamentals from a licensed data source through a new provider adapter.

## Verification

```bash
PYTHONPATH=src python -m unittest discover -s tests
python -m best_factor.cli run \
  --prices-file tests/fixtures/prices.csv \
  --universe-file tests/fixtures/universe.csv \
  --fundamentals-file tests/fixtures/fundamentals.csv \
  --output-dir /tmp/best-factor-smoke \
  --rebalance M \
  --top-n 3 \
  --factor-preset core
```
