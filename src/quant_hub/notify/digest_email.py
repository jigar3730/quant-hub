"""Launchpad daily and Lynch weekly digest emails."""

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
    "summary": "background:#f8fafc;border-left:4px solid #2563eb;padding:14px 16px;margin:16px 0;border-radius:0 6px 6px 0",
    "card": "border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;margin:10px 0;background:#fff",
    "meta": "font-size:12px;color:#64748b;margin-top:4px",
    "why": "font-size:13px;color:#475569;line-height:1.45;margin-top:8px",
    "tier1": "display:inline-block;background:#dcfce7;color:#166534;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px",
    "tier2": "display:inline-block;background:#dbeafe;color:#1e40af;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px",
    "tier3": "display:inline-block;background:#f1f5f9;color:#475569;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px",
    "lynch": "display:inline-block;background:#f3e8ff;color:#6b21a8;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px",
    "footer": "font-size:11px;color:#94a3b8;margin-top:24px;line-height:1.5",
    "highlights": "font-size:12px;color:#64748b;margin-top:6px;padding-left:16px",
    "setup": "font-size:13px;color:#0f172a;margin-top:8px;background:#f8fafc;padding:8px 10px;border-radius:6px",
    "universe_header": "font-size:19px;margin:28px 0 4px;border-top:1px solid #e2e8f0;padding-top:20px",
}


def _esc(value: Any) -> str:
    return "—" if value is None else html.escape(str(value))


def _finviz_link(ticker: str, *, bold: bool = True) -> str:
    """Generates an HTML anchor tag pointing to Finviz for a given ticker symbol."""
    symbol = html.escape(ticker.upper())
    weight = "font-weight:bold;font-size:16px;" if bold else ""
    return (
        f'<a href="https://finviz.com/quote.ashx?t={symbol}" '
        f'target="_blank" '
        f'style="{weight}color:#2563eb;text-decoration:none">{symbol}</a>'
    )

def _summary(lines: list[str]) -> str:
    items = "".join(f"<li style='margin-bottom:6px'>{_esc(line)}</li>" for line in lines)
    return f'<div style="{_STYLES["summary"]}"><ul style="margin:0;padding-left:18px">{items}</ul></div>'


def _regime_chip(regime: dict[str, Any]) -> str:
    parts = [f"Market: <strong>{_esc(regime.get('label', 'unknown'))}</strong>"]
    if regime.get("spy_price") is not None:
        parts.append(f"SPY ${float(regime['spy_price']):.0f}")
    if regime.get("return_63d_pct") is not None:
        parts.append(f"{float(regime['return_63d_pct']):+.1f}% (63d)")
    return f'<p style="font-size:14px;color:#475569;margin:0 0 12px">{" · ".join(parts)}</p>'


def _launchpad_card(row: dict[str, Any], *, badge_style: str) -> str:
    sector = row.get("sector_etf")
    sector_line = f'<div style="{_STYLES["meta"]}">Sector ETF: {_esc(sector)}</div>' if sector else ""
    highlights = row.get("factor_highlights") or []
    highlights_html = ""
    if highlights:
        items = "".join(f"<li>{_esc(item)}</li>" for item in highlights)
        highlights_html = f'<ul style="{_STYLES["highlights"]}">{items}</ul>'
    setup_html = f'<div style="{_STYLES["setup"]}">{_esc(row["setup"])}</div>' if row.get("setup") else ""
    return f"""
    <div style="{_STYLES["card"]}">
      <div>{_finviz_link(row["ticker"])}
        <span style="{badge_style};margin-left:8px">{_esc(row.get("tier_label") or row.get("tier"))}</span>
        <span style="float:right;font-weight:bold;font-size:15px">{format_score(row.get("final_score"))}</span>
      </div>
      {sector_line}
      <div style="{_STYLES["why"]}">{_esc(row.get("why") or row.get("tier_reason") or "")}</div>
      {highlights_html}
      {setup_html}
    </div>"""


def _launchpad_section(rows: list[dict[str, Any]], *, title: str, badge_style: str, empty: str = "") -> str:
    body = "".join(_launchpad_card(row, badge_style=badge_style) for row in rows)
    if not body:
        if not empty:
            return ""
        body = f'<p style="color:#64748b;font-size:14px">{html.escape(empty)}</p>'
    return f'<h4 style="font-size:15px;margin:18px 0 6px">{html.escape(title)}</h4>{body}'


def _changes_block(universe: dict[str, Any]) -> str:
    new = ", ".join(universe.get("new_entrants") or []) or "—"
    dropped = ", ".join(universe.get("dropped") or []) or "—"
    persistent = ", ".join(
        f"{row['ticker']} ({row['days_actionable']}d)"
        for row in universe.get("persistent") or []
    ) or "—"
    return f"""
    <div style="background:#f1f5f9;border-radius:8px;padding:10px 14px;margin:10px 0;font-size:13px">
      <strong>New today:</strong> {html.escape(new)}<br>
      <strong>Dropped:</strong> {html.escape(dropped)}<br>
      <strong>Held 3+ days:</strong> {html.escape(persistent)}
    </div>"""


def _universe_section(universe: dict[str, Any]) -> str:
    tier1 = universe.get("tier1") or []
    tier2 = universe.get("tier2") or []
    near_misses = universe.get("near_misses") or []
    count = len(tier1) + len(tier2)
    label = _esc(universe.get("universe_label") or universe.get("universe_id"))

    body = ""
    if count:
        body += _launchpad_section(tier1, title="High-conviction setups", badge_style=_STYLES["tier1"])
        body += _launchpad_section(tier2, title="Watchlist", badge_style=_STYLES["tier2"])
    elif near_misses:
        body += (
            '<p style="color:#64748b;font-size:14px;margin:6px 0">'
            "No qualified setups today."
            "</p>"
        )
        body += _launchpad_section(
            near_misses,
            title="Closest to qualifying",
            badge_style=_STYLES["tier3"],
        )
    else:
        body += '<p style="color:#64748b;font-size:14px;margin:6px 0">No qualified setups or near-misses today.</p>'

    return f"""
    <h3 style="{_STYLES["universe_header"]}">{label} — {count} actionable</h3>
    {_changes_block(universe)}
    {body}"""


def build_daily_digest_email(payload: dict[str, Any]) -> tuple[str, str]:
    scan_date = date.fromisoformat(payload["scan_date"])
    universes = payload.get("universes") or []
    totals = payload.get("totals") or {}
    count = totals.get("actionable", 0)
    tier1_count = totals.get("tier1", 0)
    day = scan_date.strftime("%A")
    if not count:
        subject = f"{day} Launchpad brief: no qualified setups"
    elif tier1_count:
        subject = f"{day} Launchpad brief: {count} setup{'s' if count != 1 else ''} ({tier1_count} high conviction)"
    else:
        subject = f"{day} Launchpad brief: {count} watchlist setup{'s' if count != 1 else ''}"

    sections = "".join(_universe_section(universe) for universe in universes)

    html_doc = f"""
    <html><body style="{_STYLES["body"]}">
    <div style="{_STYLES["header"]}">
      <h1 style="margin:0;font-size:22px">Daily Launchpad Brief</h1>
      <p style="margin:8px 0 0;opacity:0.85">{scan_date:%A, %B %d, %Y}</p>
    </div>
    <div style="{_STYLES["content"]}">
      {_summary(daily_executive_summary(payload))}
      {_regime_chip(payload.get("regime") or {})}
      {sections}
      <p style="{_STYLES["footer"]}">{_esc(payload.get("policy_footer"))}</p>
    </div></body></html>"""
    return subject, html_doc


def _lynch_card(row: dict[str, Any]) -> str:
    company = f'<div style="{_STYLES["meta"]}">{_esc(row["company_name"])}</div>' if row.get("company_name") else ""
    return f"""
    <div style="{_STYLES["card"]}">
      <div>{_finviz_link(row["ticker"])}
        <span style="{_STYLES["lynch"]};margin-left:8px">{_esc(row.get("category_label"))}</span>
        <span style="float:right;font-weight:bold">{format_score(row.get("lynch_score"))}</span>
      </div>
      {company}
      <div style="{_STYLES["meta"]}">PEG {_esc(row.get("peg_label"))}</div>
      <div style="{_STYLES["why"]}">{_esc(row.get("why") or "")}</div>
    </div>"""


def _overlap_card(row: dict[str, Any]) -> str:
    launchpad, lynch = row["launchpad"], row["lynch"]
    return f"""
    <div style="{_STYLES["card"]};border-left:4px solid #16a34a">
      <div>{_finviz_link(row["ticker"])}
        <span style="{_STYLES["tier1"]};margin-left:8px">Launchpad + Lynch</span>
      </div>
      <div style="{_STYLES["meta"]}">Launchpad {format_score(launchpad.get("final_score"))} · Lynch {format_score(lynch.get("lynch_score"))} · {_esc(lynch.get("category_label"))}</div>
      <div style="{_STYLES["why"]}">{_esc(launchpad.get("why") or lynch.get("why") or "")}</div>
    </div>"""


def build_weekly_digest_email(payload: dict[str, Any]) -> tuple[str, str]:
    lynch_date = date.fromisoformat(payload["lynch_date"])
    lynch = payload.get("lynch_top") or []
    overlap = payload.get("launchpad_overlap") or []
    subject = (
        f"Week ending {lynch_date:%b %d}: {len(lynch)} Lynch pick{'s' if len(lynch) != 1 else ''}"
        f" · {len(overlap)} Launchpad overlap{'s' if len(overlap) != 1 else ''}"
    )
    overlap_html = "".join(_overlap_card(row) for row in overlap) or (
        '<p style="color:#64748b;font-size:14px">No recent Launchpad names overlap this week’s Lynch ranking.</p>'
    )
    lynch_html = "".join(_lynch_card(row) for row in lynch) or (
        '<p style="color:#64748b;font-size:14px">No Lynch candidates passed this week.</p>'
    )
    launchpad_date = payload.get("launchpad_scan_date")
    metadata = f"Lynch scan {lynch_date.isoformat()}"
    if launchpad_date:
        metadata += f" · Launchpad scan {launchpad_date}"
    html_doc = f"""
    <html><body style="{_STYLES["body"]}">
    <div style="{_STYLES["header"]}">
      <h1 style="margin:0;font-size:22px">Weekly Lynch Digest</h1>
      <p style="margin:8px 0 0;opacity:0.85">Week ending {lynch_date:%B %d, %Y}</p>
    </div>
    <div style="{_STYLES["content"]}">
      {_summary(weekly_executive_summary(payload))}
      <p style="{_STYLES["meta"]}">{_esc(metadata)}</p>
      <h3 style="font-size:17px;margin:24px 0 8px">Launchpad ∩ Lynch</h3>
      {overlap_html}
      <h3 style="font-size:17px;margin:24px 0 8px">Peter Lynch top candidates</h3>
      {lynch_html}
      <p style="{_STYLES["footer"]}">{_esc(payload.get("policy_footer"))}</p>
    </div></body></html>"""
    return subject, html_doc


def send_daily_digest(payload: dict[str, Any], *, config: EmailConfig | None = None) -> bool:
    subject, html_doc = build_daily_digest_email(payload)
    return send_html_email(subject, html_doc, config=config)


def send_weekly_digest(payload: dict[str, Any], *, config: EmailConfig | None = None) -> bool:
    subject, html_doc = build_weekly_digest_email(payload)
    return send_html_email(subject, html_doc, config=config)
