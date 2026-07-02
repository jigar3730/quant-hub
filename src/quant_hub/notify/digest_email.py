"""Consolidated daily and weekly digest emails."""

from __future__ import annotations

import html
from datetime import date
from typing import Any

from quant_hub.digest.humanize import (
    daily_executive_summary,
    format_score,
    weekly_executive_summary,
)
from quant_hub.notify.email import EmailConfig, send_html_email

_STYLES = {
    "body": "font-family:Segoe UI,Arial,sans-serif;color:#1e293b;max-width:860px;margin:0",
    "header": "background:#0f172a;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0",
    "content": "padding:20px 24px;background:#fff;border:1px solid #e2e8f0;border-top:none;border-radius:0 0 8px 8px",
    "summary_box": "background:#f8fafc;border-left:4px solid #2563eb;padding:14px 16px;margin:16px 0;border-radius:0 6px 6px 0",
    "card": "border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;margin:10px 0;background:#fff",
    "why": "font-size:13px;color:#475569;line-height:1.45;margin-top:8px",
    "meta": "font-size:12px;color:#64748b;margin-top:4px",
    "badge_t1": "display:inline-block;background:#dcfce7;color:#166534;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px",
    "badge_t2": "display:inline-block;background:#dbeafe;color:#1e40af;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px",
    "badge_swing": "display:inline-block;background:#fef3c7;color:#92400e;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px",
    "badge_lynch": "display:inline-block;background:#f3e8ff;color:#6b21a8;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px",
    "footer": "font-size:11px;color:#94a3b8;margin-top:24px;line-height:1.5",
}


def _esc(value: Any) -> str:
    if value is None:
        return "—"
    return html.escape(str(value))


def _tv_link(ticker: str, *, bold: bool = True) -> str:
    sym = html.escape(ticker)
    weight = "font-weight:bold;font-size:16px;" if bold else ""
    return (
        f'<a href="https://www.tradingview.com/chart/?symbol={sym}" '
        f'style="{weight}color:#2563eb;text-decoration:none">{sym}</a>'
    )


def _exec_summary(lines: list[str]) -> str:
    items = "".join(f"<li style='margin-bottom:6px'>{_esc(line)}</li>" for line in lines)
    return f'<div style="{_STYLES["summary_box"]}"><ul style="margin:0;padding-left:18px">{items}</ul></div>'


def _regime_chip(regime: dict) -> str:
    label = _esc(regime.get("label", "unknown"))
    spy = regime.get("spy_price")
    ret = regime.get("return_63d_pct")
    parts = [f"Market: <strong>{label}</strong>"]
    if spy is not None:
        parts.append(f"SPY ${float(spy):.0f}")
    if ret is not None:
        parts.append(f"+{float(ret):.1f}% (63d)")
    mult = regime.get("multiplier")
    if mult is not None:
        parts.append(f"regime ×{float(mult):.2f}")
    return f'<p style="font-size:14px;color:#475569;margin:0 0 12px">{" · ".join(parts)}</p>'


def _breakout_card(row: dict, *, badge_style: str) -> str:
    tier_label = row.get("tier_label") or row.get("tier")
    why = row.get("why") or row.get("tier_reason") or ""
    sector = row.get("sector_etf")
    sector_line = (
        f'<div style="{_STYLES["meta"]}">Sector ETF: {_esc(sector)}</div>' if sector else ""
    )
    return f"""
    <div style="{_STYLES["card"]}">
      <div>
        {_tv_link(row["ticker"])}
        <span style="{badge_style};margin-left:8px">{_esc(tier_label)}</span>
        <span style="float:right;font-weight:bold;font-size:15px">{format_score(row.get("final_score"))}</span>
      </div>
      {sector_line}
      <div style="{_STYLES["why"]}">{_esc(why)}</div>
    </div>"""


def _breakout_section(rows: list[dict], *, title: str, badge_style: str, empty_msg: str) -> str:
    if not rows:
        return f"""
        <h3 style="font-size:17px;margin:24px 0 8px">{html.escape(title)}</h3>
        <p style="color:#64748b;font-size:14px">{html.escape(empty_msg)}</p>"""
    cards = "".join(_breakout_card(r, badge_style=badge_style) for r in rows)
    return f"""
    <h3 style="font-size:17px;margin:24px 0 8px">{html.escape(title)}</h3>
    {cards}"""


def _changes_block(payload: dict) -> str:
    new = payload.get("new_entrants") or []
    dropped = payload.get("dropped") or []
    persist = payload.get("persistent") or []
    if not new and not dropped and not persist:
        return ""
    new_txt = ", ".join(new) or "—"
    drop_txt = ", ".join(dropped) or "—"
    persist_txt = ", ".join(f"{p['ticker']} ({p['days_actionable']}d)" for p in persist) or "—"
    return f"""
    <div style="background:#f1f5f9;border-radius:8px;padding:12px 16px;margin:16px 0;font-size:13px">
      <strong>New today:</strong> {html.escape(new_txt)}<br>
      <strong>Dropped:</strong> {html.escape(drop_txt)}<br>
      <strong>Held 3+ days:</strong> {html.escape(persist_txt)}
    </div>"""


def build_daily_digest_email(payload: dict) -> tuple[str, str]:
    scan_date = date.fromisoformat(payload["scan_date"])
    regime = payload.get("regime") or {}
    tier1 = payload.get("tier1") or []
    tier2 = payload.get("tier2") or []
    n_signals = len(tier1) + len(tier2)
    day_name = scan_date.strftime("%A")

    if n_signals == 0:
        subject = f"{day_name} brief: quiet breakout day · {regime.get('label', 'unknown')} market"
    elif len(tier1) and len(tier2):
        subject = (
            f"{day_name} brief: {n_signals} breakouts to watch "
            f"({len(tier1)} high conviction)"
        )
    elif len(tier1):
        subject = f"{day_name} brief: {len(tier1)} high-conviction breakout{'s' if len(tier1) != 1 else ''}"
    else:
        subject = f"{day_name} brief: {len(tier2)} watchlist breakout{'s' if len(tier2) != 1 else ''}"

    exec_html = _exec_summary(daily_executive_summary(payload))
    regime_html = _regime_chip(regime)
    changes_html = _changes_block(payload)

    tier1_html = _breakout_section(
        tier1,
        title="High conviction breakouts",
        badge_style=_STYLES["badge_t1"],
        empty_msg="No Tier 1 names today — the bar is high (norm ≥80, strong compression & volume).",
    )
    tier2_html = _breakout_section(
        tier2,
        title="Watchlist breakouts",
        badge_style=_STYLES["badge_t2"],
        empty_msg="No Tier 2 watchlist names today.",
    )

    html_doc = f"""
    <html><body style="{_STYLES["body"]}">
    <div style="{_STYLES["header"]}">
      <h1 style="margin:0;font-size:22px">Daily Breakout Brief</h1>
      <p style="margin:8px 0 0;opacity:0.85">{scan_date:%A, %B %d, %Y}</p>
    </div>
    <div style="{_STYLES["content"]}">
      {exec_html}
      {regime_html}
      {changes_html}
      {tier1_html}
      {tier2_html}
      <p style="{_STYLES["footer"]}">{_esc(payload.get("policy_footer"))}</p>
    </div>
    </body></html>
    """
    return subject, html_doc


def _triple_card(row: dict) -> str:
    b = row["breakout"]
    s = row["swing"]
    ly = row["lynch"]
    why_parts = [p for p in (b.get("why"), s.get("why"), ly.get("why")) if p]
    why = " ".join(why_parts[:2])
    return f"""
    <div style="{_STYLES["card"]};border-left:4px solid #16a34a">
      <div>
        {_tv_link(row["ticker"])}
        <span style="{_STYLES["badge_t1"]};margin-left:8px">Triple alignment</span>
      </div>
      <div style="{_STYLES["meta"]}">
        Breakout {format_score(b.get("final_score"))} ·
        Swing {format_score(s.get("swing_score"))} ·
        Lynch {format_score(ly.get("lynch_score"))} ·
        {_esc(ly.get("category_label") or ", ".join(ly.get("categories") or []))}
      </div>
      <div style="{_STYLES["why"]}">{_esc(why)}</div>
    </div>"""


def _swing_card(row: dict) -> str:
    tier_label = row.get("tier_label") or row.get("tier")
    grade = row.get("grade_label") or row.get("quality_label")
    rsi = row.get("rsi")
    rsi_line = f" · RSI {float(rsi):.0f}" if rsi is not None else ""
    return f"""
    <div style="{_STYLES["card"]}">
      <div>
        {_tv_link(row["ticker"])}
        <span style="{_STYLES["badge_swing"]};margin-left:8px">{_esc(tier_label)}</span>
        <span style="float:right;font-weight:bold">{format_score(row.get("swing_score"))}</span>
      </div>
      <div style="{_STYLES["meta"]}">{_esc(grade)}{rsi_line}</div>
      <div style="{_STYLES["why"]}">{_esc(row.get("why") or "")}</div>
    </div>"""


def _lynch_card(row: dict) -> str:
    name = row.get("company_name")
    name_line = f'<div style="{_STYLES["meta"]}">{_esc(name)}</div>' if name else ""
    peg = row.get("peg_label") or format_score(row.get("peg_ratio"))
    return f"""
    <div style="{_STYLES["card"]}">
      <div>
        {_tv_link(row["ticker"])}
        <span style="{_STYLES["badge_lynch"]};margin-left:8px">{_esc(row.get("category_label"))}</span>
        <span style="float:right;font-weight:bold">{format_score(row.get("lynch_score"))}</span>
      </div>
      {name_line}
      <div style="{_STYLES["meta"]}">PEG {peg}</div>
      <div style="{_STYLES["why"]}">{_esc(row.get("why") or row.get("tier_reason") or "")}</div>
    </div>"""


def build_weekly_digest_email(payload: dict) -> tuple[str, str]:
    lynch_date = date.fromisoformat(payload["lynch_date"])
    triple = payload.get("triple_alignment") or []
    swing = payload.get("swing_highlights") or []
    lynch = payload.get("lynch_top") or []

    subject = (
        f"Week ending {lynch_date:%b %d}: "
        f"{len(triple)} triple hit{'s' if len(triple) != 1 else ''} · "
        f"{len(swing)} swing idea{'s' if len(swing) != 1 else ''} · "
        f"{len(lynch)} Lynch pick{'s' if len(lynch) != 1 else ''}"
    )

    exec_html = _exec_summary(weekly_executive_summary(payload))

    if triple:
        triple_html = f"""
        <h3 style="font-size:17px;margin:24px 0 8px">Triple alignment — breakout + swing + Lynch</h3>
        {"".join(_triple_card(r) for r in triple)}"""
    else:
        triple_html = """
        <h3 style="font-size:17px;margin:24px 0 8px">Triple alignment</h3>
        <p style="color:#64748b;font-size:14px">No names hit all three screens this week. Check swing and Lynch sections below.</p>"""

    swing_list = payload.get("swing_highlights") or []
    if swing_list:
        swing_html = f"""
        <h3 style="font-size:17px;margin:24px 0 8px">Swing pullback setups</h3>
        <p style="font-size:13px;color:#64748b;margin:0 0 10px">Grade A/B weekly pullbacks into the trend (score ≥70).</p>
        {"".join(_swing_card(s) for s in swing_list)}"""
    else:
        swing_html = """
        <h3 style="font-size:17px;margin:24px 0 8px">Swing pullback setups</h3>
        <p style="color:#64748b;font-size:14px">No A/B swing setups this week.</p>"""

    lynch_list = payload.get("lynch_top") or []
    if lynch_list:
        lynch_html = f"""
        <h3 style="font-size:17px;margin:24px 0 8px">Peter Lynch value picks</h3>
        <p style="font-size:13px;color:#64748b;margin:0 0 10px">Passed quantitative Lynch checks — sorted by score.</p>
        {"".join(_lynch_card(ly) for ly in lynch_list)}"""
    else:
        lynch_html = """
        <h3 style="font-size:17px;margin:24px 0 8px">Peter Lynch value picks</h3>
        <p style="color:#64748b;font-size:14px">No Lynch passes this week — filters are strict by design.</p>"""

    regime_lines = ""
    for r in payload.get("regime_week") or []:
        regime_lines += (
            f"<li>{_esc(r['scan_date'])}: <strong>{_esc(r['regime_label'])}</strong> — "
            f"{_esc(r['actionable_count'])} actionable breakout(s)</li>"
        )
    regime_html = (
        f"""
        <h3 style="font-size:17px;margin:24px 0 8px">Breakout regime this week</h3>
        <ul style="font-size:14px;color:#475569">{regime_lines}</ul>"""
        if regime_lines
        else ""
    )

    etf_lines = ""
    for e in payload.get("etf_highlights") or []:
        etf_lines += (
            f"<li>{_tv_link(e['ticker'], bold=False)}: "
            f"breakout {_esc(e.get('breakout_tier'))}, swing {_esc(e.get('swing_tier'))}</li>"
        )
    etf_html = (
        f"""
        <h3 style="font-size:17px;margin:24px 0 8px">Sector & commodity ETFs</h3>
        <ul style="font-size:14px">{etf_lines}</ul>"""
        if etf_lines
        else ""
    )

    scan_meta = (
        f"Swing scan {_esc(payload.get('swing_scan_date'))} · "
        f"Breakout {_esc(payload.get('breakout_scan_date'))} · "
        f"Lynch {_esc(payload.get('lynch_date'))}"
    )

    html_doc = f"""
    <html><body style="{_STYLES["body"]}">
    <div style="{_STYLES["header"]}">
      <h1 style="margin:0;font-size:22px">Weekly Quant Digest</h1>
      <p style="margin:8px 0 0;opacity:0.85">Week ending {lynch_date:%B %d, %Y}</p>
    </div>
    <div style="{_STYLES["content"]}">
      {exec_html}
      <p style="font-size:13px;color:#64748b;margin:0 0 16px">{scan_meta}</p>
      {triple_html}
      {swing_html}
      {lynch_html}
      {regime_html}
      {etf_html}
      <p style="{_STYLES["footer"]}">{_esc(payload.get("policy_footer"))}</p>
    </div>
    </body></html>
    """
    return subject, html_doc


def send_daily_digest(payload: dict, *, config: EmailConfig | None = None) -> bool:
    subject, html_doc = build_daily_digest_email(payload)
    return send_html_email(subject, html_doc, config=config)


def send_weekly_digest(payload: dict, *, config: EmailConfig | None = None) -> bool:
    subject, html_doc = build_weekly_digest_email(payload)
    return send_html_email(subject, html_doc, config=config)
