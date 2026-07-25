# best-factor

`best-factor` is a dependency-light Python CLI for researching which long-only US equity factor ranks highest among tested candidates in a given run under free-data constraints. It maps each tested factor to actual stock holdings and weights, backtests weekly or monthly rebalancing, ranks factors with return and downside metrics, and writes CSV, Markdown, and static HTML dashboard reports.

> Research only: this project does **not** provide investment advice or trade execution.

## What it does

- Loads a US stock universe and long-form OHLCV prices from CSV, or optionally fetches live prices through `yfinance`, a direct Yahoo chart JSON adapter, or a yfinance-primary/Yahoo-chart fallback chain.
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
  --provider yfinance_yahoo_chart \
  --tickers AAPL MSFT NVDA AMZN META GOOGL JPM XOM LLY AVGO \
  --period 5y \
  --output-dir runs/live-smoke \
  --rebalance M \
  --top-n 5 \
  --factor-preset zoo
```

The recommended live provider is `yfinance_yahoo_chart`: it downloads with yfinance first and then fills yfinance-missing tickers through a direct Yahoo chart JSON request path. `--provider yfinance` and `--provider yahoo_chart` remain available for diagnostics. The live path is intentionally optional because free public data can fail, be rate-limited, or change format.

## Output artifacts

Each run writes:

- `factor_metrics.csv`
- `factor_rankings.csv`
- `factor_holdout_metrics.csv`
- `factor_holdout_rankings.csv`
- `latest_holdings.csv`
- `portfolio_returns.csv`
- `benchmark_returns.csv`
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

It must not deploy to, trigger workflows in, or reuse assets from another repository or Pages site. The shared 11-project navigation may link to sibling dashboards, but no sibling project is a deployment target for this repository.

The `docs/` dashboard separates two kinds of controls:

- **Analysis inputs** change the Python run: history period, rebalance frequency, holding-count cap, weighting, factor scope, market-cap/liquidity gates, and transaction-cost assumptions.
- **Display settings** only change the current browser view: chart sort, visible rows, metric, and observation date.

The page validates the type, range, and safe syntax of all 11 analysis inputs and prepares a complete `gh workflow run` command. The workflow then revalidates the full contract, including factor names against the Python registry, before any live run. The optional control-API connection is disabled by default. When a deployment configures an HTTPS base URL and the reviewer enters a short-lived bearer token, the browser may submit an authenticated run; the token remains memory-only and is not written to browser storage. The client keeps draft, pending, currently displayed, and verified-bound results separate and never treats an API failure as permission to run the copied command.

```bash
gh workflow run update-dashboard.yml \
  --repo SonChangGi/best-factor \
  --ref main \
  --raw-field 'period=5y' \
  --raw-field 'rebalance=M' \
  --raw-field 'top_n=20' \
  --raw-field 'weighting=score' \
  --raw-field 'factor_preset=zoo' \
  --raw-field 'factor_allowlist=__preset__' \
  --raw-field 'min_market_cap=10000000000' \
  --raw-field 'min_dollar_volume=50000000' \
  --raw-field 'eligibility_adv_window=63' \
  --raw-field 'transaction_cost_bps=5' \
  --raw-field 'transaction_cost_model=one_way_notional'
```

`factor_allowlist=__preset__` explicitly clears a previously saved allowlist and uses the selected preset. Empty manual fields keep the previously saved value. A successful manual run saves the normalized configuration in `.github/best-factor-dashboard-config.json`, publishes a safe public copy at `docs/data/dashboard-config.json`, and binds that copy to the generated result timestamp, source hash, and data date. The next scheduled run reuses the same settings. Failed generation does not replace the saved configuration or public result.

The control API contract is `POST /v1/projects/best-factor/runs`, `GET /v1/runs/{runId}`, and `GET /v1/runs/{runId}/result`. Requests use `inputSchemaVersion: "best-factor/v1"`, all 11 `inputs`, and `allowFallback: false`. The browser accepts only the public statuses `queued`, `dispatched`, `running`, `validating`, `published`, `failed`, and `cancelled`, and its two-hour polling budget covers the workflow's 90-minute limit. Before replacing the in-memory static payload it requires matching `requestedInputs`, `normalizedInputs`, `effectiveInputs`, empty `ignoredInputs` and `fallbacks`, `fallbackUsed: false`, `fallbackReason: null`, `configHashAlgorithm: "best-factor-python-json-v1"`, the authoritative server `configHash`, matching `effectiveConfigHash`, `inputSchemaHash`, run/schema identity, `dataIdentity` (`source`, `sourceHash`, `dataAsOf`), `dataAsOf`, `calculatedAt`, `codeVersion`, and artifact `url`, `sha256`, `byteSize`, and `contractVersion: "best-factor/latest-results/v1"`. The independently downloaded byte length and SHA-256 must match the binding, and the allowlisted bounded summary derived from that full JSON must be semantically equal to the API result `payload`. Because this public client always sends `allowFallback: false`, `effectiveConfigHash` must equal `configHash`. The committed Pages JSON remains the startup and failure fallback.

When the control API dispatches this GitHub workflow, it sets the separate `control_run_id`, `control_input_schema_version`, `control_input_schema_hash`, `control_config_hash_algorithm`, and `control_config_hash` inputs. The workflow validates the identifier and binding before analysis and includes the run ID in the Actions run name and log, so orchestration never correlates work by “latest run.” After committing and deploying the generated data it downloads the commit-addressed immutable `latest-results.json` from the exact data commit, requires byte equality with the generated file, and sends that artifact identity in the protected worker callback. A control run fails if callback secrets are absent or if any binding/readback check fails. Direct and scheduled runs leave `control_run_id` blank, are labeled `direct`, and skip the callback.

The workflow installs the live-data extra, runs network-free tests plus syntax/static import checks before live generation, archives each generated run artifact, and uses GitHub Pages custom workflow deployment (`actions/configure-pages`, `actions/upload-pages-artifact`, and `actions/deploy-pages`) so the generated `docs/` artifact is published by that same run. It intentionally does not rely on a workflow self-commit to trigger a branch-based Pages build.

### Manual update automation

The only automated deployment target is `SonChangGi/best-factor`. Live-data cron schedules are active again at 07:00 KST Tue-Sat with 09:00/11:00/13:00 KST stale-data fallbacks, and reviewed `workflow_dispatch` runs execute the same live yfinance-primary/Yahoo-chart-fallback generation path. Pushes deploy the committed `docs/` artifact; scheduled/manual refreshes sync `docs/data/latest-results.json`, `docs/data/summary.json`, the result-bound public configuration, and the persisted private configuration before Pages deployment so later pushes do not overwrite a fresher artifact with stale JSON or settings.

For scheduled and manual updates, the deployed Pages artifact remains the freshness source of truth. The freshness gate is implemented in `.github/scripts/check_dashboard_freshness.py`: the 07:00 KST primary schedule always tries to refresh, while fallback schedules skip if the public JSON is already fresh for the expected U.S. session.

### Live dashboard universe

`.github/best-factor-dashboard-tickers.txt` is the committed public dashboard priority universe. It currently targets **1,800** individual-stock priorities generated from the current Nasdaq Trader symbol directories plus a free Yahoo-family 4-month average-dollar-volume screen. It is not a survivorship-free historical universe and not the whole US market.

Each live workflow run first rebuilds a validated universe CSV from the public Nasdaq Trader `nasdaqlisted.txt` and `otherlisted.txt` symbol directories. The validator emits only conservative current common-stock rows and excludes benchmarks, ETFs, funds, preferred/depositary shares, units, warrants, rights, ADR/ADS/ordinary-share rows, unsupported symbol formats, and other non-common-stock patterns. The live run then requests prices for the validated stocks in chunks and fails closed unless all configured data-coverage gates pass:

- at least **1,700** validated current common-stock universe rows before price fetching;
- at least **1,600** unique stock tickers with successful price data;
- at least **90%** requested-price coverage;
- at least **90%** latest-date price coverage;
- at least **1,100** latest signal-date factor-eligible stocks after the configured trailing-history and liquidity diagnostics.

For large live runs, the workflow skips the raw `factor_scores.csv` archive and uses streaming factor-score/backtest construction to avoid turning the factor zoo into a massive CI artifact. The final run metadata records requested, priced, rankable, failed, coverage, source-hash, exclusion-count, and **factor-eligible** stock-count fields so the dashboard can show whether the expanded 1,600+ priced-stock and 1,100+ factor-eligible-stock requirements were met by names that also have enough trailing history and liquidity.

The workflow applies a 63-session trailing average-dollar-volume liquidity filter and charges **5 bps one-way traded notional** transaction costs by default. This means an initial full portfolio buy costs 1x notional and a full disjoint replacement costs 2x notional; the older `portfolio_turnover` convention remains available only for backward-compatible research comparisons. The dashboard also publishes latest-portfolio implementation diagnostics: effective holding count, max/top-5 concentration, minimum/weighted trailing ADV, 5%/10% ADV capacity heuristics, limiting ticker, and average/latest turnover. These are practical sanity checks, not an order-book or market-impact model.

A positive market-cap threshold first enriches the Nasdaq Trader-validated common-stock universe through the paginated yfinance US-listed equity screener, then uses a bounded per-ticker metadata fallback only for the small unresolved remainder. The universe is emitted only when every validated ticker has a finite positive market cap; scheduled and control runs therefore preserve the last good result rather than silently publishing a liquidity-only result under a market-cap configuration. A reviewed direct `workflow_dispatch` may still set the separate operational input `allow_fallback=true` to use the truthful scope `live_resilient_current_common_stock_liquidity_screen_actions` and record `market_cap_metadata_insufficient_preflight`. Other CLI/provider failures are not swallowed by that fallback. The final run metadata records whether the market-cap filter was attempted, whether it was effective, its status string, and any fallback reason so dashboard snapshots are not silently compared under different screens.

The live price adapter publishes source-chain diagnostics (`provider_order`, `provider_attempted_sources`, `provider_fill_counts`, `fallback_filled_ticker_count`, provider error counts, and failed tickers by source). This makes it visible whether the yfinance primary route was enough or the direct Yahoo chart contingency filled missing stocks. The fallback improves operational resilience but is still Yahoo-family free data, not an independent licensed feed.

The live workflow keeps overlapping benchmark symbols out of the stock universe, keeps push-time docs deploys separate from reviewed manual live refreshes, pins third-party GitHub Actions by SHA, and uses Dependabot for weekly action/Python dependency review. This keeps the public page reproducible and cheap to update, but the results remain research-grade and current-universe biased.

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
- Yahoo/yfinance and direct Yahoo chart data can be delayed, revised, rate-limited, unavailable, or subject to Yahoo terms.
- Live Yahoo-family and CSV price loaders scale `open`, `high`, `low`, and `close` to the `adj_close` basis before OHLC-derived factor scoring, preventing raw/adjusted price-scale mixing around dividends and splits.
- Current free-provider universe membership and market-cap metadata are current screens, not historical point-in-time constituent or point-in-time market-cap filters; when market-cap metadata is insufficient the dashboard labels the run as common-stock/liquidity-screened rather than large-cap-screened.
- Fundamental files must include `as_of_date` and `available_at`; rows without `available_at` are treated as non-point-in-time and skipped for historical factor scoring.
- Some factors or rows may be skipped with explicit reason codes such as `missing_fundamentals`, `insufficient_history`, `insufficient_volume`, `market_cap_unavailable`, `market_cap_below_min`, `empty_after_filters`, `provider_error`, `not_enough_assets`, `missing_rebalance_price`, `missing_exit_price`, `invalid_period_missing_price`, `inactive_or_non_stock`, and dynamic `zero_coverage:<factor>` diagnostics.
- Factor-zoo mode compares many related definitions. The top-ranked factor can be an in-sample winner caused by multiple-testing/data-snooping. The reported recent-tail holdout rank is a robustness diagnostic, not proof of a universal anomaly; recheck with true holdout periods, alternate universes, costs, and higher-quality point-in-time data before drawing investment conclusions.
- Default live results include a simple transaction-cost haircut and an ADV capacity heuristic, but they still do not model bid/ask spread variation, order-book depth, nonlinear market impact, taxes, borrow constraints, execution latency, or broker-specific fills.

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
