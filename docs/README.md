# Best Factor Lab static dashboard

This directory is a GitHub Pages-ready static site for `best-factor` outputs.

```bash
python -m best_factor.cli run \
  --prices-file tests/fixtures/prices.csv \
  --universe-file tests/fixtures/universe.csv \
  --fundamentals-file tests/fixtures/fundamentals.csv \
  --output-dir runs/fixture \
  --rebalance M \
  --top-n 3

python -m best_factor.cli site \
  --run-dir runs/fixture \
  --output-file docs/data/latest-results.json \
  --data-scope csv_run

python -m http.server --directory docs 8000
```

Open `http://127.0.0.1:8000/`. Opening `index.html` directly with `file://` may block JSON loading in some browsers, so serve the directory over HTTP or GitHub Pages.
