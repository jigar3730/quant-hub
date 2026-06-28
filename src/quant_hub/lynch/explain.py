"""Plain-English explanations for Lynch checks and metrics."""

from __future__ import annotations

from quant_hub.lynch import config as cfg

RULE_GUIDE: dict[str, dict[str, str]] = {
    "positive_earnings": {
        "label": "Profitable today",
        "why": "Lynch avoided pre-profit lottery tickets. The company must earn money now, not someday.",
    },
    "return_on_equity": {
        "label": "Returns on equity (quality)",
        "why": "Return on equity shows management turns shareholder money into profit. Weak ROE often signals a mediocre business.",
    },
    "revenue_stability": {
        "label": "Steady revenue",
        "why": "Wild revenue swings can mean one big customer or a fad. Lynch preferred predictable demand.",
    },
    "peg_ratio": {
        "label": "PEG ratio (price vs growth)",
        "why": "PEG compares the P/E to earnings growth. Below 1.0 means you may pay a fair price for the growth you get — Lynch's core idea.",
    },
    "eps_growth_5y": {
        "label": "Earnings growth",
        "why": "Lynch wanted companies growing earnings fast enough to matter, but not so fast that the story is unbelievable.",
    },
    "pe_ratio": {
        "label": "P/E ratio (price tag)",
        "why": "The P/E is what you pay per $1 of annual profit. Lower can mean cheaper, but context matters for growth stocks.",
    },
    "debt_to_equity": {
        "label": "Debt load",
        "why": "Too much debt magnifies problems in a downturn. Lynch liked companies that could survive bad years.",
    },
    "financial_strength": {
        "label": "Balance sheet strength",
        "why": "Either manageable debt or more cash than debt. Lynch hated balance sheets that could force a dilutive rescue.",
    },
    "wall_street_neglect": {
        "label": "Not over-owned by Wall Street",
        "why": "Lynch believed less institutional attention and fewer analysts can leave mispriced gems — if the business is solid.",
    },
    "insider_or_buyback": {
        "label": "Insiders buying or share count falling",
        "why": "Insiders buying with their own money, or fewer shares outstanding, aligns management with shareholders.",
    },
    "market_cap": {
        "label": "Company size",
        "why": "Fast growers need room to multiply — Lynch's 10-baggers often started smaller. Stalwarts are large, proven franchises.",
    },
    "eps_growth": {
        "label": "Earnings growth (category)",
        "why": "Category-specific growth hurdle for fast growers vs steady stalwarts.",
    },
    "dividend_yield": {
        "label": "Dividend yield",
        "why": "Stalwarts often pay you to wait while earnings compound at a moderate pace.",
    },
    "price_to_book": {
        "label": "Price vs book value",
        "why": "Asset plays trade below the accounting value of the business — potential hidden value if assets are real.",
    },
    "net_cash_to_price": {
        "label": "Net cash per share vs stock price",
        "why": "If cash on the balance sheet is a large fraction of the share price, you may get the operating business cheaply.",
    },
}


def _fmt_money(value) -> str:
    if value is None:
        return "unknown"
    try:
        v = float(value)
        if abs(v) >= 1_000_000_000:
            return f"${v / 1_000_000_000:.1f} billion"
        if abs(v) >= 1_000_000:
            return f"${v / 1_000_000:.0f} million"
        return f"${v:,.0f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_pct(value) -> str:
    if value is None:
        return "unknown"
    try:
        v = float(value)
        if abs(v) <= 1.5:
            return f"{v * 100:.1f}%"
        return f"{v:.1f}%"
    except (TypeError, ValueError):
        return str(value)


def _fmt_ratio(value, *, decimals: int = 2) -> str:
    if value is None:
        return "unknown"
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def format_metric_plain(rule: str, value, metrics: dict) -> str:
    """Turn a raw metric into a sentence a non-analyst can read."""
    if rule in ("peg_ratio", "pe_ratio", "price_to_book", "debt_to_equity"):
        return _fmt_ratio(value)
    if rule in ("eps_growth_5y", "eps_growth", "return_on_equity", "dividend_yield"):
        return _fmt_pct(value)
    if rule == "market_cap":
        return _fmt_money(value)
    if rule == "net_cash_positive":
        return _fmt_money(value)
    if rule == "financial_strength":
        if isinstance(value, dict):
            nc = value.get("net_cash")
            de = value.get("debt_to_equity")
        else:
            nc = metrics.get("net_cash")
            de = metrics.get("debt_to_equity")
        if nc is not None and float(nc) > 0:
            return f"Net cash {_fmt_money(nc)}"
        if de is not None:
            return f"Debt/equity {_fmt_ratio(de)}"
        return "balance sheet data limited"
    if rule == "wall_street_neglect":
        if isinstance(value, dict):
            return (
                f"{value.get('institutional_pct', 'unknown')}% institutional ownership, "
                f"{value.get('analysts', 'unknown')} analysts"
            )
        return str(value)
    if rule == "insider_or_buyback":
        if isinstance(value, dict):
            ins = value.get("insider_purchases_6m")
            chg = value.get("shares_change_yoy")
            parts = []
            if ins is not None:
                parts.append(f"insider buys {ins:,.0f} shares (6m)")
            if chg is not None:
                parts.append(f"share count change {_fmt_pct(chg)} YoY")
            return "; ".join(parts) if parts else "no insider/share data"
        return str(value)
    if rule == "positive_earnings":
        eps = metrics.get("trailing_eps")
        return f"${_fmt_ratio(eps)}" if eps is not None else "unknown"
    if rule == "revenue_stability":
        return f"revenue volatility {_fmt_ratio(value)}" if value is not None else "unknown"
    if rule == "net_cash_to_price":
        return _fmt_pct(value)
    return str(value) if value is not None else "unknown"


def result_sentence(rule: str, passed: bool, value, metrics: dict, threshold: str) -> str:
    plain = format_metric_plain(rule, value, metrics)
    guide = RULE_GUIDE.get(rule, {})
    label = guide.get("label", rule.replace("_", " ").title())

    if passed:
        if rule == "peg_ratio" and value is not None and float(value) <= cfg.PEG_BARGAIN:
            return f"✓ {label}: {plain} — excellent bargain (PEG under {cfg.PEG_BARGAIN})."
        return f"✓ {label}: {plain} — meets Lynch hurdle ({threshold})."
    if value is None:
        return f"✗ {label}: data missing — could not verify ({threshold})."
    return f"✗ {label}: {plain} — does not meet Lynch hurdle ({threshold})."


def enrich_checks(checks: list[dict], metrics: dict) -> list[dict]:
    enriched = []
    for check in checks:
        rule = check.get("rule", "")
        guide = RULE_GUIDE.get(rule, {})
        passed = bool(check.get("passed"))
        value = check.get("value")
        threshold = check.get("threshold", "")
        row = dict(check)
        row["label"] = guide.get("label", rule.replace("_", " ").title())
        row["why_it_matters"] = guide.get("why", check.get("detail", ""))
        row["plain_value"] = format_metric_plain(rule, value, metrics)
        row["result_text"] = result_sentence(rule, passed, value, metrics, threshold)
        enriched.append(row)
    return enriched


def build_investor_summary(
    metrics: dict,
    checks: list[dict],
    *,
    passed: bool,
    categories: list[str],
) -> str:
    name = metrics.get("company_name") or metrics.get("ticker", "")
    ticker = metrics.get("ticker", "")
    pe = metrics.get("pe_ratio")
    peg = metrics.get("peg_ratio")
    growth = metrics.get("eps_growth_for_peg") or metrics.get("eps_growth_5y")
    growth_label = metrics.get("eps_growth_source", "5y CAGR")

    parts = [f"{ticker} ({name})" if name else ticker]

    if pe is not None and peg is not None and growth is not None:
        parts.append(
            f"trades at { _fmt_ratio(pe) }× trailing earnings with "
            f"{ _fmt_pct(growth) } {growth_label} growth (PEG { _fmt_ratio(peg) })."
        )
    elif pe is not None:
        parts.append(f"trades at { _fmt_ratio(pe) }× trailing earnings.")

    if categories:
        labels = ", ".join(c.replace("_", " ").title() for c in categories)
        parts.append(f"Fits Lynch {labels} profile.")
    elif passed:
        parts.append("Passes the quantitative Lynch screen.")
    else:
        failed = [c for c in checks if not c.get("passed")]
        if failed:
            top = failed[0]
            label = top.get("label") or top.get("rule", "check")
            parts.append(f"Did not pass mainly on {label.lower()}.")
        else:
            parts.append("Did not pass the quantitative Lynch screen.")

    de = metrics.get("debt_to_equity")
    nc = metrics.get("net_cash")
    if nc is not None and nc > 0:
        parts.append(f"Balance sheet: net cash { _fmt_money(nc) }.")
    elif de is not None:
        parts.append(f"Balance sheet: debt/equity { _fmt_ratio(de) }.")

    rev_g = metrics.get("revenue_growth")
    if rev_g is not None:
        parts.append(f"Revenue growth (Yahoo TTM proxy): { _fmt_pct(rev_g) }.")

    return " ".join(parts)


def build_fundamental_snapshot(metrics: dict) -> list[dict]:
    """Key metrics with source and plain explanation for dashboard/email."""
    rows = []

    def add(key: str, label: str, value, explanation: str, source: str = "") -> None:
        rows.append(
            {
                "metric": key,
                "label": label,
                "value": value,
                "display": format_metric_plain(key if key in RULE_GUIDE else "pe_ratio", value, metrics)
                if key not in ("market_cap", "net_cash", "price")
                else _fmt_money(value),
                "explanation": explanation,
                "source": source,
            }
        )

    pe_src = metrics.get("pe_source", "Yahoo Finance")
    add(
        "pe_ratio",
        "P/E (trailing)",
        metrics.get("pe_ratio"),
        "Price divided by last 12 months of earnings per share — your 'price tag' on current profits.",
        pe_src,
    )
    add(
        "peg_ratio",
        "PEG ratio",
        metrics.get("peg_ratio"),
        "P/E divided by earnings growth (%). Lynch liked PEG near or below 1 — growth at a reasonable price.",
        metrics.get("peg_source", "computed"),
    )
    growth = metrics.get("eps_growth_for_peg")
    add(
        "eps_growth",
        "Earnings growth (for PEG)",
        growth,
        metrics.get(
            "eps_growth_explanation",
            "Growth rate used in PEG — prefers recent TTM trend, then 5-year CAGR.",
        ),
        metrics.get("eps_growth_source", ""),
    )
    g5 = metrics.get("eps_growth_5y")
    rows.append(
        {
            "metric": "eps_growth_5y",
            "label": "EPS 5-year CAGR",
            "value": g5,
            "display": _fmt_pct(g5),
            "explanation": "Longer-term compound growth from quarterly EPS — smooths one-off years.",
            "source": "quarterly income statement",
        }
    )
    add(
        "debt_to_equity",
        "Debt / equity",
        metrics.get("debt_to_equity"),
        "Total debt vs shareholder equity. Lower generally means less financial stress.",
        "Yahoo Finance",
    )
    add(
        "net_cash",
        "Net cash",
        metrics.get("net_cash"),
        "Cash minus total debt. Positive means cash on hand exceeds borrowings.",
        "Yahoo Finance balance sheet",
    )
    add(
        "market_cap",
        "Market cap",
        metrics.get("market_cap"),
        "Total market value of all shares — size bucket for fast grower vs stalwart.",
        "Yahoo Finance",
    )
    add(
        "price_to_book",
        "Price / book",
        metrics.get("price_to_book"),
        "Stock price vs accounting book value per share — key for asset plays.",
        "Yahoo Finance",
    )
    inst = metrics.get("institutional_ownership")
    rows.append(
        {
            "metric": "institutional_ownership",
            "label": "Institutional ownership",
            "value": inst,
            "display": _fmt_pct(inst),
            "explanation": "Percent of shares held by funds/institutions. Lynch sometimes liked lower figures (less crowded).",
            "source": "Yahoo Finance",
        }
    )
    return rows
