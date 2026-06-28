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
          <td>{s.get('final_adjusted_score', 0):.1f}</td>
          <td>{t.get('sector_etf', '')}</td>
          <td>{rs}</td>
          <td>{comp}</td>
          <td>{vol}</td>
          <td>{t.get('tier_reason', '')}</td>
        </tr>"""

    if not rows_html:
        rows_html = "<tr><td colspan='8'>No actionable tickers today.</td></tr>"

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
      <tr><th>Ticker</th><th>Tier</th><th>Score</th><th>ETF</th>
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
