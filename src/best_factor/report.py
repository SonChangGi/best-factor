"""Markdown and static HTML report writers."""
from __future__ import annotations

import html
import math
from collections import Counter
from pathlib import Path

from .schemas import CAVEATS, TIMING_CONVENTION


def write_report(
    path: str | Path,
    rankings: list[dict[str, object]],
    latest_holdings: list[dict[str, object]],
    skipped_reasons: dict[str, int],
    metadata: dict[str, object],
) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    best = rankings[0] if rankings else None
    lines: list[str] = []
    lines.append("# Best Factor Backtest Report")
    lines.append("")
    lines.append("## Summary")
    if best:
        lines.append(f"- **Best factor**: `{best['factor']}`")
        lines.append(f"- **Composite score**: {_fmt(best.get('composite_score'))}")
        lines.append(f"- **CAGR**: {_pct(best.get('cagr'))}")
        lines.append(f"- **Sharpe**: {_fmt(best.get('sharpe'))}")
        lines.append(f"- **Sortino**: {_fmt(best.get('sortino'))}")
        lines.append(f"- **Calmar**: {_fmt(best.get('calmar'))}")
        lines.append(f"- **Max drawdown (MDD)**: {_pct(best.get('max_drawdown'))}")
    else:
        lines.append("No effective factor portfolios were produced.")
    lines.append("")
    lines.append("## Timing convention")
    lines.append(TIMING_CONVENTION)
    lines.append("")
    lines.append("## Factor rankings")
    lines.append("| Rank | Factor | Composite | CAGR | Sharpe | Sortino | Calmar | MDD | Volatility | Coverage |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in rankings:
        lines.append(
            "| {rank} | {factor} | {score} | {cagr} | {sharpe} | {sortino} | {calmar} | {mdd} | {vol} | {coverage} |".format(
                rank=row.get("rank", ""),
                factor=row.get("factor", ""),
                score=_fmt(row.get("composite_score")),
                cagr=_pct(row.get("cagr")),
                sharpe=_fmt(row.get("sharpe")),
                sortino=_fmt(row.get("sortino")),
                calmar=_fmt(row.get("calmar")),
                mdd=_pct(row.get("max_drawdown")),
                vol=_pct(row.get("volatility")),
                coverage=_pct(row.get("coverage")),
            )
        )
    lines.append("")
    lines.append("## Latest best-factor holdings")
    if latest_holdings:
        lines.append("| Rebalance date | Ticker | Weight | Score | Price date used |")
        lines.append("|---|---|---:|---:|---|")
        for row in latest_holdings:
            lines.append(
                f"| {_date(row.get('rebalance_date'))} | {row.get('ticker')} | {_pct(row.get('weight'))} | {_fmt(row.get('score'))} | {_date(row.get('price_date_used'))} |"
            )
    else:
        lines.append("No latest holdings were available for the selected best factor.")
    lines.append("")
    lines.append("## Skipped factor/row diagnostics")
    tested = int(metadata.get("tested_factor_count", 0) or 0)
    effective = int(metadata.get("effective_factor_count", 0) or 0)
    skipped_count = max(0, tested - effective)
    lines.append(f"- Tested factors: {tested}")
    lines.append(f"- Effective factors: {effective}")
    lines.append(f"- Skipped factors: {skipped_count}")
    if skipped_reasons:
        lines.append("")
        lines.append("| Reason | Count |")
        lines.append("|---|---:|")
        for reason, count in Counter(skipped_reasons).most_common():
            lines.append(f"| `{reason}` | {count} |")
    lines.append("")
    lines.append("## Data sources and run metadata")
    for key in ["provider", "provider_version", "source", "fetched_at", "cache_dir", "universe_as_of_date", "source_hash"]:
        if metadata.get(key) not in (None, ""):
            lines.append(f"- {key}: `{metadata.get(key)}`")
    lines.append("")
    lines.append("## Free-data limitations and warnings")
    caveats = metadata.get("caveats") or CAVEATS
    for caveat in caveats:
        lines.append(f"- {caveat}")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("The top-ranked factor is the best result under this run's universe, timing, filters, ranking formula, and free-data limitations. Re-run with different universes, windows, costs, and data sources before relying on any conclusion.")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_html_report(
    path: str | Path,
    rankings: list[dict[str, object]],
    latest_holdings: list[dict[str, object]],
    skipped_reasons: dict[str, int],
    metadata: dict[str, object],
) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    best = rankings[0] if rankings else None
    caveats = metadata.get("caveats") or CAVEATS
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Best Factor Dashboard</title>",
        "<style>",
        _css(),
        "</style>",
        "</head>",
        "<body>",
        '<main class="page" aria-labelledby="page-title">',
        '<section class="hero" aria-labelledby="page-title">',
        '<p class="eyebrow">Research dashboard</p>',
        '<h1 id="page-title">Best Factor Dashboard</h1>',
        _hero_summary(best, metadata),
        "</section>",
        _ranking_section(rankings),
        _metrics_section(rankings),
        _holdings_section(latest_holdings),
        _diagnostics_section(skipped_reasons, metadata),
        _metadata_section(metadata),
        _caveats_section(caveats),
        "</main>",
        "</body>",
        "</html>",
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _hero_summary(best: dict[str, object] | None, metadata: dict[str, object]) -> str:
    if not best:
        return '<div class="summary-card warning">No effective factor portfolio was produced.</div>'
    cards = [
        ("Best factor", f"<strong>{_e(best.get('factor'))}</strong>"),
        ("Composite", _fmt(best.get("composite_score"))),
        ("CAGR", _pct(best.get("cagr"))),
        ("Sharpe", _fmt(best.get("sharpe"))),
        ("Sortino", _fmt(best.get("sortino"))),
        ("Calmar", _fmt(best.get("calmar"))),
        ("MDD", _pct(best.get("max_drawdown"))),
        ("Provider", _e(metadata.get("provider", "unknown"))),
    ]
    body = ["<div class=\"summary-grid\">"]
    for label, value in cards:
        body.append(f'<article class="summary-card"><span>{_e(label)}</span><b>{value}</b></article>')
    body.append("</div>")
    body.append(f'<p class="interpretation">{_e(TIMING_CONVENTION)}</p>')
    return "\n".join(body)


def _ranking_section(rankings: list[dict[str, object]]) -> str:
    lines = ['<section class="panel" aria-labelledby="ranking-title">', '<h2 id="ranking-title">Factor Ranking</h2>']
    lines.append('<p class="section-note">Bars show clamped composite scores for quick scanning; exact metric values remain visible.</p>')
    if not rankings:
        lines.append('<p class="empty">No rank-eligible factors.</p>')
    else:
        lines.append('<div class="ranking-list" role="list">')
        for row in rankings[:12]:
            width = _bar_width(float_or_zero(row.get("composite_score")) * 100)
            lines.append(
                '<article class="rank-card" role="listitem">'
                f'<div class="rank-head"><span class="rank">#{_e(row.get("rank"))}</span><strong>{_e(row.get("factor"))}</strong><span>{_fmt(row.get("composite_score"))}</span></div>'
                f'<div class="bar" aria-label="Composite score {_fmt(row.get("composite_score"))}"><span style="width: {width:.2f}%"></span></div>'
                f'<div class="metric-row"><span>CAGR {_pct(row.get("cagr"))}</span><span>Sharpe {_fmt(row.get("sharpe"))}</span><span>MDD {_pct(row.get("max_drawdown"))}</span></div>'
                "</article>"
            )
        lines.append("</div>")
    lines.append("</section>")
    return "\n".join(lines)


def _metrics_section(rankings: list[dict[str, object]]) -> str:
    lines = ['<section class="panel" aria-labelledby="metrics-title">', '<h2 id="metrics-title">Risk And Return Metrics</h2>']
    lines.append('<div class="table-wrap"><table aria-label="Factor risk and return metrics">')
    lines.append("<caption>Factor comparison. Numeric values are authoritative; bars are normalized visual aids.</caption>")
    lines.append("<thead><tr><th>Rank</th><th>Factor</th><th>CAGR</th><th>Sharpe</th><th>Sortino</th><th>Calmar</th><th>MDD</th><th>Volatility</th><th>Coverage</th></tr></thead><tbody>")
    if not rankings:
        lines.append('<tr><td colspan="9">No metrics available.</td></tr>')
    for row in rankings:
        lines.append(
            "<tr>"
            f"<td>{_e(row.get('rank'))}</td>"
            f"<td>{_e(row.get('factor'))}</td>"
            f"<td>{_metric_cell(row.get('cagr'), pct=True)}</td>"
            f"<td>{_metric_cell(row.get('sharpe'))}</td>"
            f"<td>{_metric_cell(row.get('sortino'))}</td>"
            f"<td>{_metric_cell(row.get('calmar'))}</td>"
            f"<td>{_metric_cell(row.get('max_drawdown'), pct=True, magnitude=True)}</td>"
            f"<td>{_metric_cell(row.get('volatility'), pct=True)}</td>"
            f"<td>{_metric_cell(row.get('coverage'), pct=True)}</td>"
            "</tr>"
        )
    lines.append("</tbody></table></div></section>")
    return "\n".join(lines)


def _holdings_section(latest_holdings: list[dict[str, object]]) -> str:
    lines = ['<section class="panel" aria-labelledby="holdings-title">', '<h2 id="holdings-title">Latest Holdings</h2>']
    if not latest_holdings:
        lines.append('<p class="empty">No latest holdings were available for the selected best factor.</p>')
    else:
        lines.append('<div class="table-wrap"><table aria-label="Latest best-factor holdings and weights">')
        lines.append("<caption>Latest selected holdings. Weight bars are clamped to 0-100% and labels show exact weights.</caption>")
        lines.append("<thead><tr><th>Ticker</th><th>Weight</th><th>Score</th><th>Rebalance date</th><th>Price date used</th></tr></thead><tbody>")
        for row in latest_holdings:
            width = _bar_width(float_or_zero(row.get("weight")) * 100)
            lines.append(
                "<tr>"
                f"<td><strong>{_e(row.get('ticker'))}</strong></td>"
                f'<td><div class="weight-cell"><div class="bar small" aria-label="Weight {_pct(row.get("weight"))}"><span style="width: {width:.2f}%"></span></div><span>{_pct(row.get("weight"))}</span></div></td>'
                f"<td>{_fmt(row.get('score'))}</td>"
                f"<td>{_e(_date(row.get('rebalance_date')))}</td>"
                f"<td>{_e(_date(row.get('price_date_used')))}</td>"
                "</tr>"
            )
        lines.append("</tbody></table></div>")
    lines.append("</section>")
    return "\n".join(lines)


def _diagnostics_section(skipped_reasons: dict[str, int], metadata: dict[str, object]) -> str:
    tested = int(metadata.get("tested_factor_count", 0) or 0)
    effective = int(metadata.get("effective_factor_count", 0) or 0)
    lines = ['<section class="panel" aria-labelledby="diagnostics-title">', '<h2 id="diagnostics-title">Diagnostics</h2>']
    lines.append(f'<div class="summary-grid compact"><article class="summary-card"><span>Tested factors</span><b>{tested}</b></article><article class="summary-card"><span>Effective factors</span><b>{effective}</b></article><article class="summary-card"><span>Skipped factors</span><b>{max(0, tested - effective)}</b></article></div>')
    if skipped_reasons:
        lines.append('<div class="table-wrap"><table aria-label="Skipped factor and row diagnostics"><caption>Skipped diagnostics by reason code.</caption><thead><tr><th>Reason</th><th>Count</th></tr></thead><tbody>')
        for reason, count in Counter(skipped_reasons).most_common():
            lines.append(f"<tr><td>{_e(reason)}</td><td>{int(count)}</td></tr>")
        lines.append("</tbody></table></div>")
    else:
        lines.append('<p class="empty">No skipped diagnostics were recorded.</p>')
    lines.append("</section>")
    return "\n".join(lines)


def _metadata_section(metadata: dict[str, object]) -> str:
    keys = ["provider", "provider_version", "source", "fetched_at", "cache_dir", "universe_as_of_date", "source_hash"]
    lines = ['<section class="panel" aria-labelledby="metadata-title">', '<h2 id="metadata-title">Run Metadata</h2>']
    lines.append('<div class="table-wrap"><table aria-label="Run metadata"><caption>Data source and reproducibility metadata.</caption><tbody>')
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            lines.append(f"<tr><th>{_e(key)}</th><td>{_e(value)}</td></tr>")
    lines.append("</tbody></table></div></section>")
    return "\n".join(lines)


def _caveats_section(caveats: object) -> str:
    lines = ['<section class="panel caveats" aria-labelledby="caveats-title">', '<h2 id="caveats-title">Free-Data Limitations</h2>']
    lines.append("<ul>")
    for caveat in caveats if isinstance(caveats, list) else CAVEATS:
        lines.append(f"<li>{_e(caveat)}</li>")
    lines.append("<li>This dashboard is a research artifact, not investment advice or a trade instruction.</li>")
    lines.append("</ul></section>")
    return "\n".join(lines)


def _metric_cell(value: object, pct: bool = False, magnitude: bool = False) -> str:
    numeric = abs(float_or_zero(value)) if magnitude else float_or_zero(value)
    width = _bar_width(numeric * 100 if pct else numeric * 10)
    label = _pct(value) if pct else _fmt(value)
    return f'<div class="metric-cell"><span class="value">{_e(label)}</span><div class="bar mini" aria-label="{_e(label)}"><span style="width: {width:.2f}%"></span></div></div>'


def _css() -> str:
    return """
:root { color-scheme: light; --ink:#17211b; --muted:#5f6f66; --paper:#f6f1e8; --panel:#fffdf7; --line:#ded3c0; --accent:#0f766e; --accent2:#d97706; --danger:#9f1239; }
* { box-sizing: border-box; }
body { margin:0; font-family: Georgia, 'Times New Roman', serif; color:var(--ink); background: radial-gradient(circle at top left, #e7f2ef 0, transparent 34rem), linear-gradient(135deg, #fbf4e4, #eef5f1); }
.page { width:min(1180px, calc(100% - 32px)); margin:0 auto; padding:32px 0 56px; }
.hero { padding:32px; border:1px solid var(--line); border-radius:28px; background:rgba(255,253,247,.9); box-shadow:0 24px 60px rgba(35,31,23,.12); }
.eyebrow { margin:0 0 8px; text-transform:uppercase; letter-spacing:.16em; color:var(--accent); font:700 12px system-ui, sans-serif; }
h1 { margin:0 0 20px; font-size:clamp(36px, 6vw, 72px); line-height:.95; }
h2 { margin:0 0 14px; font-size:clamp(24px, 3vw, 36px); }
.summary-grid { display:grid; grid-template-columns:repeat(auto-fit, minmax(145px, 1fr)); gap:12px; }
.summary-grid.compact { margin:8px 0 18px; }
.summary-card { padding:16px; border:1px solid var(--line); border-radius:18px; background:#fffaf0; }
.summary-card span { display:block; color:var(--muted); font:700 12px system-ui, sans-serif; text-transform:uppercase; letter-spacing:.08em; }
.summary-card b { display:block; margin-top:8px; font-size:22px; overflow-wrap:anywhere; }
.interpretation, .section-note, .empty { color:var(--muted); line-height:1.55; }
.panel { margin-top:20px; padding:24px; border:1px solid var(--line); border-radius:24px; background:rgba(255,253,247,.86); }
.ranking-list { display:grid; gap:12px; }
.rank-card { padding:16px; border:1px solid var(--line); border-radius:18px; background:#fffaf0; }
.rank-head, .metric-row { display:flex; gap:12px; align-items:center; justify-content:space-between; flex-wrap:wrap; }
.rank { color:var(--accent2); font:800 13px system-ui, sans-serif; }
.metric-row { margin-top:10px; color:var(--muted); font:700 13px system-ui, sans-serif; }
.bar { height:14px; margin-top:12px; border-radius:999px; background:#eadfcd; overflow:hidden; border:1px solid #d7c8ae; }
.bar span { display:block; height:100%; background:linear-gradient(90deg, var(--accent), #14b8a6); }
.bar.small { width:min(180px, 50vw); margin:0; }
.bar.mini { width:92px; height:9px; margin:0; }
.table-wrap { width:100%; overflow:auto; }
table { width:100%; border-collapse:collapse; font:15px system-ui, sans-serif; }
caption { text-align:left; color:var(--muted); margin:0 0 10px; font-weight:700; }
th, td { padding:11px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:middle; }
th { color:#33433a; background:#f5eddf; }
.metric-cell, .weight-cell { display:flex; gap:10px; align-items:center; min-width:150px; }
.metric-cell .value { min-width:70px; font-variant-numeric:tabular-nums; }
.caveats li { margin:8px 0; line-height:1.5; }
.warning { border-color:var(--danger); }
@media (max-width: 720px) { .page { width:min(100% - 18px, 1180px); padding-top:12px; } .hero, .panel { padding:18px; border-radius:18px; } th, td { padding:9px 8px; } }
""".strip()


def _e(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _bar_width(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(numeric):
        return 0.0
    return max(0.0, min(100.0, numeric))


def float_or_zero(value: object) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return numeric if math.isfinite(numeric) else 0.0


def _fmt(value: object) -> str:
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return ""


def _pct(value: object) -> str:
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return ""


def _date(value: object) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")
