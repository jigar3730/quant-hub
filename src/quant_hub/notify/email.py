from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


@dataclass
class EmailConfig:
    host: str
    port: int
    user: str
    password: str
    from_addr: str
    to_addrs: list[str]
    use_tls: bool = True

    @classmethod
    def from_env(cls) -> EmailConfig | None:
        to_raw = os.environ.get("EMAIL_TO", "")
        host = os.environ.get("SMTP_HOST", "")
        if not to_raw or not host:
            return None
        return cls(
            host=host,
            port=int(os.environ.get("SMTP_PORT", "587")),
            user=os.environ.get("SMTP_USER", ""),
            password=os.environ.get("SMTP_PASSWORD", ""),
            from_addr=os.environ.get("EMAIL_FROM", os.environ.get("SMTP_USER", "")),
            to_addrs=[a.strip() for a in to_raw.split(",") if a.strip()],
            use_tls=os.environ.get("SMTP_USE_TLS", "true").lower() != "false",
        )


def get_actionable_tickers(report: dict) -> list[dict]:
    return [t for t in report.get("tickers", []) if t.get("tier") in ("Tier 1", "Tier 2")]


def build_actionable_email(
    report: dict,
    *,
    scan_date: date | None = None,
) -> tuple[str, str]:
    scan_date = scan_date or date.today()
    summary = report["scan_summary"]
    regime = report["market_regime"]
    tiers = summary["tier_counts"]
    actionable = get_actionable_tickers(report)

    subject = (
        f"Quant Hub {scan_date:%Y-%m-%d}: "
        f"{len(actionable)} Actionable "
        f"({tiers['Tier 1']} T1, {tiers['Tier 2']} T2)"
    )

    rows_html = ""
    for t in sorted(actionable, key=lambda x: x["summary"]["final_adjusted_score"], reverse=True):
        s = t["summary"]
        scores = t.get("scores") or {}
        rs = scores.get("rs_market", {}).get("score", "-")
        comp = scores.get("compression", {}).get("score", "-")
        vol = scores.get("relative_volume", {}).get("score", "-")
        ticker = t["ticker"]
        tv_link = f"https://www.tradingview.com/chart/?symbol={ticker}"
        ticker_cell = f'<a href="{tv_link}">{ticker}</a>'
        rows_html += f"""
        <tr>
          <td>{ticker_cell}</td>
          <td>{t['tier']}</td>
          <td>{s.get('normalized_score', 0):.1f}</td>
          <td>{s.get('final_adjusted_score', 0):.1f}</td>
          <td>{t.get('sector_etf', '')}</td>
          <td>{rs}</td>
          <td>{comp}</td>
          <td>{vol}</td>
          <td>{t.get('tier_reason', '')}</td>
        </tr>"""

    if not rows_html:
        rows_html = "<tr><td colspan='9'>No actionable tickers today.</td></tr>"

    html = f"""
    <html><body>
    <h2>Quant Hub Breakout Scan — {scan_date:%Y-%m-%d}</h2>
    <p>Regime: {regime['label']} (×{regime['multiplier']}) |
       SPY ${regime.get('spy_price', '—')} |
       63d: {regime.get('return_63d_pct', '—')}%</p>
    <p>Universe: {summary['universe_size']} scanned,
       {summary['eligible_count']} eligible,
       {len(actionable)} actionable</p>
    <table border="1" cellpadding="4">
      <tr><th>Ticker</th><th>Tier</th><th>Norm</th><th>Final</th><th>ETF</th>
          <th>RS</th><th>Compress</th><th>Vol</th><th>Reason</th></tr>
      {rows_html}
    </table>
    </body></html>
    """
    return subject, html


def send_scan_email(
    report: dict,
    *,
    config: EmailConfig | None = None,
    scan_date: date | None = None,
) -> bool:
    config = config or EmailConfig.from_env()
    if not config:
        return False

    subject, html = build_actionable_email(report, scan_date=scan_date)
    return send_html_email(subject, html, config=config)


def send_html_email(
    subject: str,
    html: str,
    *,
    config: EmailConfig | None = None,
) -> bool:
    config = config or EmailConfig.from_env()
    if not config:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.from_addr
    msg["To"] = ", ".join(config.to_addrs)
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(config.host, config.port, timeout=30) as server:
        if config.use_tls:
            server.starttls()
        if config.user and config.password:
            server.login(config.user, config.password)
        server.sendmail(config.from_addr, config.to_addrs, msg.as_string())

    return True


def build_swing_email(
    report: dict,
    *,
    scan_date: date | None = None,
) -> tuple[str, str]:
    scan_date = scan_date or date.today()
    summary = report["scan_summary"]
    setups = report.get("tickers", [])
    longs = [t for t in setups if t.get("tier") == "SETUP_LONG"]
    shorts = [t for t in setups if t.get("tier") == "SETUP_SHORT"]

    subject = (
        f"Quant Hub Swing {scan_date:%Y-%m-%d}: "
        f"{len(setups)} setups ({len(longs)} long, {len(shorts)} short)"
    )

    rows_html = ""
    for t in sorted(setups, key=lambda x: (x.get("tier", ""), x["ticker"])):
        detail = t.get("setup_detail") or {}
        scores = t.get("scores") or {}
        ticker = t["ticker"]
        tv_link = f"https://www.tradingview.com/chart/?symbol={ticker}"
        rows_html += f"""
        <tr>
          <td><a href="{tv_link}">{ticker}</a></td>
          <td>{t.get('tier', '')}</td>
          <td>{detail.get('close', '—')}</td>
          <td>{scores.get('ema20', {}).get('score', '—')}</td>
          <td>{scores.get('ema50', {}).get('score', '—')}</td>
          <td>{scores.get('rsi', {}).get('score', '—')}</td>
          <td>{scores.get('atr', {}).get('score', '—')}</td>
          <td>{t.get('tier_reason', '')}</td>
        </tr>"""

    if not rows_html:
        rows_html = "<tr><td colspan='8'>No swing setups this week.</td></tr>"

    regime = report.get("market_regime", {})
    html = f"""
    <html><body>
    <h2>Quant Hub Weekly Swing Scan — {scan_date:%Y-%m-%d}</h2>
    <p>Data: {regime.get('period', '10y')} / {regime.get('interval', '1wk')} weekly OHLCV</p>
    <p>Universe: {summary['universe_size']} scanned —
       {summary.get('setup_long_count', len(longs))} long,
       {summary.get('setup_short_count', len(shorts))} short setups</p>
    <table border="1" cellpadding="4">
      <tr><th>Ticker</th><th>Setup</th><th>Close</th><th>EMA20</th><th>EMA50</th>
          <th>RSI</th><th>ATR</th><th>Notes</th></tr>
      {rows_html}
    </table>
    <p><small>SETUP_LONG: pullback into rising 20EMA. SETUP_SHORT: pullback into falling 20EMA.</small></p>
    </body></html>
    """
    return subject, html


def send_swing_email(
    report: dict,
    *,
    config: EmailConfig | None = None,
    scan_date: date | None = None,
) -> bool:
    config = config or EmailConfig.from_env()
    if not config:
        return False

    subject, html = build_swing_email(report, scan_date=scan_date)
    return send_html_email(subject, html, config=config)


def _fmt_lynch_pct(value) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
        if abs(v) <= 1.5:
            return f"{v * 100:.1f}%"
        return f"{v:.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _fmt_lynch_num(value, *, decimals: int = 2) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_lynch_mcap(value) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
        if v >= 1_000_000_000_000:
            return f"${v / 1_000_000_000_000:.1f}T"
        if v >= 1_000_000_000:
            return f"${v / 1_000_000_000:.1f}B"
        if v >= 1_000_000:
            return f"${v / 1_000_000:.0f}M"
        return f"${v:,.0f}"
    except (TypeError, ValueError):
        return str(value)


def _lynch_category_badges(categories: list[str]) -> str:
    if not categories:
        return '<span style="color:#64748b">Base screen</span>'
    colors = {
        "fast_grower": "#16a34a",
        "stalwart": "#2563eb",
        "asset_play": "#9333ea",
    }
    labels = {
        "fast_grower": "Fast Grower",
        "stalwart": "Stalwart",
        "asset_play": "Asset Play",
    }
    parts = []
    for cat in categories:
        color = colors.get(cat, "#64748b")
        label = labels.get(cat, cat.replace("_", " ").title())
        parts.append(
            f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:4px;margin-right:4px;font-size:12px">{label}</span>'
        )
    return " ".join(parts)


def build_lynch_email(
    report: dict,
    *,
    scan_date: date | None = None,
) -> tuple[str, str]:
    scan_date = scan_date or date.today()
    summary = report["scan_summary"]
    candidates = report.get("candidates") or []
    cats = summary.get("category_counts", {})
    preset_label = summary.get("preset_label", "Peter Lynch Screen")
    universe_id = report.get("universe_id", "sp500")
    passed = summary.get("passed_count", len(candidates))
    scanned = summary.get("universe_size", 0)

    subject = (
        f"Your Lynch Stock Ideas — {scan_date:%b %d}: "
        f"{passed} name{'s' if passed != 1 else ''} passed"
    )

    intro = (
        f"We screened <strong>{scanned}</strong> stocks ({universe_id}) using "
        f"<strong>{preset_label}</strong>. "
        f"<strong>{passed}</strong> passed Peter Lynch's quantitative checks."
    )
    if passed == 0:
        intro += " Nothing met the bar this run — review the dashboard for near-misses."

    summary_cards = f"""
    <table cellpadding="8" cellspacing="0" style="margin:16px 0;border-collapse:separate">
      <tr>
        <td style="background:#f0fdf4;border-radius:8px;text-align:center;min-width:100px">
          <div style="font-size:24px;font-weight:bold;color:#16a34a">{cats.get('fast_grower', 0)}</div>
          <div style="font-size:12px;color:#166534">Fast Growers</div>
        </td>
        <td style="background:#eff6ff;border-radius:8px;text-align:center;min-width:100px">
          <div style="font-size:24px;font-weight:bold;color:#2563eb">{cats.get('stalwart', 0)}</div>
          <div style="font-size:12px;color:#1e40af">Stalwarts</div>
        </td>
        <td style="background:#faf5ff;border-radius:8px;text-align:center;min-width:100px">
          <div style="font-size:24px;font-weight:bold;color:#9333ea">{cats.get('asset_play', 0)}</div>
          <div style="font-size:12px;color:#6b21a8">Asset Plays</div>
        </td>
      </tr>
    </table>
    """

    rows_html = ""
    for t in candidates[:20]:
        ticker = t["ticker"]
        tv_link = f"https://www.tradingview.com/chart/?symbol={ticker}"
        name = t.get("company_name") or ""
        badges = _lynch_category_badges(t.get("categories") or [])
        score = t.get("lynch_score", 0)
        reason = t.get("tier_reason") or ""
        summary = t.get("investor_summary") or ""
        summary_cell = (
            f'<div style="font-size:12px;color:#475569;margin-top:4px">{summary}</div>'
            if summary
            else ""
        )
        rows_html += f"""
        <tr style="border-bottom:1px solid #e2e8f0">
          <td style="padding:10px 8px">
            <a href="{tv_link}" style="font-weight:bold;font-size:15px">{ticker}</a>
            <div style="font-size:12px;color:#64748b">{name}</div>
            {summary_cell}
          </td>
          <td style="padding:10px 8px">{badges}</td>
          <td style="padding:10px 8px;text-align:center;font-weight:bold">{score:.0f}</td>
          <td style="padding:10px 8px">{_fmt_lynch_num(t.get('pe_ratio'))}</td>
          <td style="padding:10px 8px">{_fmt_lynch_num(t.get('peg_ratio'))}</td>
          <td style="padding:10px 8px">{_fmt_lynch_pct(t.get('eps_growth_5y_pct'))}</td>
          <td style="padding:10px 8px">{_fmt_lynch_mcap(t.get('market_cap'))}</td>
          <td style="padding:10px 8px;font-size:12px;color:#475569">{reason}</td>
        </tr>"""

    if not rows_html:
        rows_html = """
        <tr><td colspan="8" style="padding:20px;text-align:center;color:#64748b">
          No stocks passed the Lynch screen this time. This is normal — the filters are strict.
          Open the Quant Hub dashboard to see which names came close.
        </td></tr>"""

    overlay = report.get("qualitative_overlay") or []
    overlay_html = "".join(f"<li style='margin-bottom:6px'>{note}</li>" for note in overlay)

    html = f"""
    <html><body style="font-family:Segoe UI,Arial,sans-serif;color:#1e293b;max-width:900px">
    <div style="background:#0f172a;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0">
      <h1 style="margin:0;font-size:22px">Peter Lynch Stock Ideas</h1>
      <p style="margin:8px 0 0;opacity:0.85">{scan_date:%A, %B %d, %Y}</p>
    </div>
    <div style="padding:20px 24px;background:#fff;border:1px solid #e2e8f0;border-top:none">
      <p style="font-size:15px;line-height:1.5">{intro}</p>
      {summary_cards}
      <h2 style="font-size:18px;margin:24px 0 12px">Top candidates</h2>
      <p style="font-size:13px;color:#64748b;margin:0 0 12px">
        Sorted by Lynch score (higher = more checks passed). Click a ticker for charts.
      </p>
      <table cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;font-size:14px">
        <tr style="background:#f8fafc;font-size:12px;color:#475569">
          <th style="padding:8px;text-align:left">Stock</th>
          <th style="padding:8px;text-align:left">Type</th>
          <th style="padding:8px">Score</th>
          <th style="padding:8px">P/E</th>
          <th style="padding:8px">PEG</th>
          <th style="padding:8px">EPS Gr 5Y</th>
          <th style="padding:8px">Market Cap</th>
          <th style="padding:8px;text-align:left">Why it passed</th>
        </tr>
        {rows_html}
      </table>
      <h2 style="font-size:16px;margin:28px 0 10px">Before you buy — ask yourself</h2>
      <ul style="font-size:14px;color:#334155;line-height:1.6;padding-left:20px">
        {overlay_html}
      </ul>
      <p style="font-size:12px;color:#94a3b8;margin-top:24px;border-top:1px solid #e2e8f0;padding-top:12px">
        Research only — not financial advice. Quant Hub Lynch screen uses public Yahoo Finance data.
        P/E, PEG, and growth figures may lag or be unavailable for some tickers.
      </p>
    </div>
    </body></html>
    """
    return subject, html


def send_lynch_email(
    report: dict,
    *,
    config: EmailConfig | None = None,
    scan_date: date | None = None,
) -> bool:
    config = config or EmailConfig.from_env()
    if not config:
        return False

    subject, html = build_lynch_email(report, scan_date=scan_date)
    return send_html_email(subject, html, config=config)
