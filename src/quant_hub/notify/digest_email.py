"""Consolidated daily and weekly digest emails."""

from __future__ import annotations

import html
from datetime import date
from typing import Any

from quant_hub.notify.email import EmailConfig, send_html_email


def _esc(value: Any) -> str:
    if value is None:
        return "—"
    return html.escape(str(value))


def _tv_link(ticker: str) -> str:
    sym = html.escape(ticker)
    return f'<a href="https://www.tradingview.com/chart/?symbol={sym}">{sym}</a>'


def _breakout_table(rows: list[dict], *, title: str) -> str:
    if not rows:
        return f"<h3>{html.escape(title)}</h3><p><em>None this period.</em></p>"
    body = ""
    for r in rows:
        body += f"""
        <tr>
          <td>{_tv_link(r['ticker'])}</td>
          <td>{_esc(r.get('tier'))}</td>
          <td>{_esc(r.get('final_score'))}</td>
          <td>{_esc(r.get('sector_etf'))}</td>
        </tr>"""
    return f"""
    <h3>{html.escape(title)}</h3>
    <table border="1" cellpadding="4">
      <tr><th>Ticker</th><th>Tier</th><th>Score</th><th>Sector ETF</th></tr>
      {body}
    </table>"""


def build_daily_digest_email(payload: dict) -> tuple[str, str]:
    scan_date = date.fromisoformat(payload["scan_date"])
    regime = payload.get("regime") or {}
    tier1 = payload.get("tier1") or []
    tier2 = payload.get("tier2") or []
    n_signals = len(tier1) + len(tier2)

    subject = f"Quant Hub Daily {scan_date:%Y-%m-%d}: {len(tier1)} conviction, {len(tier2)} watchlist"

    new_html = ", ".join(payload.get("new_entrants") or []) or "—"
    drop_html = ", ".join(payload.get("dropped") or []) or "—"
    persist = payload.get("persistent") or []
    persist_html = ", ".join(f"{p['ticker']} ({p['days_actionable']}d)" for p in persist) or "—"

    if n_signals == 0:
        intro = (
            f"<p><strong>No Tier 1 or Tier 2 breakout signals today.</strong> "
            f"Regime: {_esc(regime.get('label'))}.</p>"
        )
    else:
        intro = (
            f"<p>Regime: <strong>{_esc(regime.get('label'))}</strong> (×{_esc(regime.get('multiplier'))}) | "
            f"SPY ${_esc(regime.get('spy_price'))} | "
            f"63d: {_esc(regime.get('return_63d_pct'))}%</p>"
        )

    html_doc = f"""
    <html><body style="font-family:Segoe UI,Arial,sans-serif;color:#1e293b;max-width:800px">
    <h2>Quant Hub Daily Digest — {scan_date:%A, %B %d}</h2>
    {intro}
    <p><strong>New today:</strong> {html.escape(new_html)}<br>
       <strong>Dropped:</strong> {html.escape(drop_html)}<br>
       <strong>Persistent (≥3d):</strong> {html.escape(persist_html)}</p>
    {_breakout_table(tier1, title="Tier 1 — High conviction")}
    {_breakout_table(tier2, title="Tier 2 — Watchlist")}
    <p style="font-size:11px;color:#64748b;margin-top:20px">{_esc(payload.get('policy_footer'))}</p>
    </body></html>
    """
    return subject, html_doc


def build_weekly_digest_email(payload: dict) -> tuple[str, str]:
    lynch_date = date.fromisoformat(payload["lynch_date"])
    triple = payload.get("triple_alignment") or []
    subject = f"Quant Hub Weekly {lynch_date:%Y-%m-%d}: {len(triple)} triple-alignment names"

    def _triple_rows() -> str:
        if not triple:
            return "<tr><td colspan='5'><em>No triple-alignment names this week.</em></td></tr>"
        out = ""
        for row in triple:
            b = row["breakout"]
            s = row["swing"]
            ly = row["lynch"]
            out += f"""
            <tr>
              <td>{_tv_link(row['ticker'])}</td>
              <td>{_esc(b.get('tier'))} / {_esc(b.get('final_score'))}</td>
              <td>{_esc(s.get('tier'))} / {_esc(s.get('swing_score'))}</td>
              <td>{_esc(ly.get('lynch_score'))}</td>
              <td>{_esc(', '.join(ly.get('categories') or []))}</td>
            </tr>"""
        return out

    swing_rows = ""
    for s in payload.get("swing_highlights") or []:
        swing_rows += f"""
        <tr>
          <td>{_tv_link(s['ticker'])}</td>
          <td>{_esc(s.get('tier'))}</td>
          <td>{_esc(s.get('swing_score'))}</td>
          <td>{_esc(s.get('quality_label'))}</td>
        </tr>"""
    if not swing_rows:
        swing_rows = "<tr><td colspan='4'><em>No A/B swing setups.</em></td></tr>"

    lynch_rows = ""
    for ly in payload.get("lynch_top") or []:
        lynch_rows += f"""
        <tr>
          <td>{_tv_link(ly['ticker'])}</td>
          <td>{_esc(ly.get('lynch_score'))}</td>
          <td>{_esc(ly.get('peg_ratio'))}</td>
          <td>{_esc(', '.join(ly.get('categories') or []))}</td>
        </tr>"""
    if not lynch_rows:
        lynch_rows = "<tr><td colspan='4'><em>No Lynch passes.</em></td></tr>"

    regime_lines = ""
    for r in payload.get("regime_week") or []:
        regime_lines += f"<li>{_esc(r['scan_date'])}: {_esc(r['regime_label'])} — {_esc(r['actionable_count'])} actionable</li>"
    if not regime_lines:
        regime_lines = "<li>No breakout runs this week.</li>"

    etf_lines = ""
    for e in payload.get("etf_highlights") or []:
        etf_lines += f"<li>{_esc(e['ticker'])}: breakout {_esc(e.get('breakout_tier'))}, swing {_esc(e.get('swing_tier'))}</li>"
    etf_section = (
        f"<h3>Sector & commodity ETFs</h3><ul>{etf_lines}</ul>" if etf_lines else ""
    )

    html_doc = f"""
    <html><body style="font-family:Segoe UI,Arial,sans-serif;color:#1e293b;max-width:900px">
    <h2>Quant Hub Weekly Digest — week ending {lynch_date:%B %d, %Y}</h2>
    <p>Swing scan: {_esc(payload.get('swing_scan_date'))} |
       Breakout reference: {_esc(payload.get('breakout_scan_date'))} |
       Lynch: {_esc(payload.get('lynch_date'))}</p>

    <h3>Triple alignment (Breakout T1 + Swing A/B + Lynch passed)</h3>
    <table border="1" cellpadding="4">
      <tr><th>Ticker</th><th>Breakout</th><th>Swing</th><th>Lynch</th><th>Categories</th></tr>
      {_triple_rows()}
    </table>

    <h3>Swing highlights (quality ≥70)</h3>
    <table border="1" cellpadding="4">
      <tr><th>Ticker</th><th>Setup</th><th>Score</th><th>Grade</th></tr>
      {swing_rows}
    </table>

    <h3>Lynch top candidates</h3>
    <table border="1" cellpadding="4">
      <tr><th>Ticker</th><th>Score</th><th>PEG</th><th>Categories</th></tr>
      {lynch_rows}
    </table>

    <h3>Breakout regime this week</h3>
    <ul>{regime_lines}</ul>
    {etf_section}
    <p style="font-size:11px;color:#64748b;margin-top:20px">{_esc(payload.get('policy_footer'))}</p>
    </body></html>
    """
    return subject, html_doc


def send_daily_digest(payload: dict, *, config: EmailConfig | None = None) -> bool:
    subject, html_doc = build_daily_digest_email(payload)
    return send_html_email(subject, html_doc, config=config)


def send_weekly_digest(payload: dict, *, config: EmailConfig | None = None) -> bool:
    subject, html_doc = build_weekly_digest_email(payload)
    return send_html_email(subject, html_doc, config=config)
