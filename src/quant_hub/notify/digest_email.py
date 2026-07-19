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
    "lynch": "display:inline-block;background:#f3e8ff;color:#6b21a8;font-size:11px;font-weight:600;padding:2px 8px;border-radius:12px",
    "footer": "font-size:11px;color:#94a3b8;margin-top:24px;line-height:1.5",
}


def _esc(value: Any) -> str:
    return "—" if value is None else html.escape(str(value))


def _tv_link(ticker: str, *, bold: bool = True) -> str:
    symbol = html.escape(ticker)
    weight = "font-weight:bold;font-size:16px;" if bold else ""
    return (
        f'<a href="https://www.tradingview.com/chart/?symbol={symbol}" '
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
    return f"""
    <div style="{_STYLES["card"]}">
      <div>{_tv_link(row["ticker"])}
        <span style="{badge_style};margin-left:8px">{_esc(row.get("tier_label") or row.get("tier"))}</span>
        <span style="float:right;font-weight:bold;font-size:15px">{format_score(row.get("final_score"))}</span>
      </div>
      {sector_line}
      <div style="{_STYLES["why"]}">{_esc(row.get("why") or row.get("tier_reason") or "")}</div>
    </div>"""


def _launchpad_section(rows: list[dict[str, Any]], *, title: str, badge_style: str, empty: str) -> str:
    body = "".join(_launchpad_card(row, badge_style=badge_style) for row in rows)
    if not body:
        body = f'<p style="color:#64748b;font-size:14px">{html.escape(empty)}</p>'
    return f'<h3 style="font-size:17px;margin:24px 0 8px">{html.escape(title)}</h3>{body}'


def _changes_block(payload: dict[str, Any]) -> str:
    new = ", ".join(payload.get("new_entrants") or []) or "—"
    dropped = ", ".join(payload.get("dropped") or []) or "—"
    persistent = ", ".join(
        f"{row['ticker']} ({row['days_actionable']}d)"
        for row in payload.get("persistent") or []
    ) or "—"
    return f"""
    <div style="background:#f1f5f9;border-radius:8px;padding:12px 16px;margin:16px 0;font-size:13px">
      <strong>New today:</strong> {html.escape(new)}<br>
      <strong>Dropped:</strong> {html.escape(dropped)}<br>
      <strong>Held {3}+ days:</strong> {html.escape(persistent)}
    </div>"""


def build_daily_digest_email(payload: dict[str, Any]) -> tuple[str, str]:
    scan_date = date.fromisoformat(payload["scan_date"])
    tier1 = payload.get("tier1") or []
    tier2 = payload.get("tier2") or []
    count = len(tier1) + len(tier2)
    day = scan_date.strftime("%A")
    if not count:
        subject = f"{day} Launchpad brief: no qualified reversals"
    elif tier1:
        subject = f"{day} Launchpad brief: {count} reversal{'s' if count != 1 else ''} ({len(tier1)} high conviction)"
    else:
        subject = f"{day} Launchpad brief: {count} watchlist reversal{'s' if count != 1 else ''}"

    html_doc = f"""
    <html><body style="{_STYLES["body"]}">
    <div style="{_STYLES["header"]}">
      <h1 style="margin:0;font-size:22px">Daily Launchpad Brief</h1>
      <p style="margin:8px 0 0;opacity:0.85">{scan_date:%A, %B %d, %Y}</p>
    </div>
    <div style="{_STYLES["content"]}">
      {_summary(daily_executive_summary(payload))}
      {_regime_chip(payload.get("regime") or {})}
      {_changes_block(payload)}
      {_launchpad_section(tier1, title="High-conviction reversals", badge_style=_STYLES["tier1"], empty="No Tier 1 Launchpad names today.")}
      {_launchpad_section(tier2, title="Launchpad watchlist", badge_style=_STYLES["tier2"], empty="No Tier 2 watchlist names today.")}
      <p style="{_STYLES["footer"]}">{_esc(payload.get("policy_footer"))}</p>
    </div></body></html>"""
    return subject, html_doc


def _lynch_card(row: dict[str, Any]) -> str:
    company = f'<div style="{_STYLES["meta"]}">{_esc(row["company_name"])}</div>' if row.get("company_name") else ""
    return f"""
    <div style="{_STYLES["card"]}">
      <div>{_tv_link(row["ticker"])}
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
      <div>{_tv_link(row["ticker"])}
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
