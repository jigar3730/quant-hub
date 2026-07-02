"""Plain-language helpers for digest emails."""

from __future__ import annotations

from typing import Any

from quant_hub.dashboard.viz.signals import rank_components, signal_insights


def truncate(text: str, *, max_len: int = 180) -> str:
    text = " ".join(str(text).split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def format_score(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.0f}"
    except (TypeError, ValueError):
        return str(value)


def format_peg(value: Any) -> str:
    if value is None:
        return "—"
    try:
        v = float(value)
        if v < 0:
            return "neg earnings"
        return f"{v:.2f}"
    except (TypeError, ValueError):
        return str(value)


def friendly_breakout_tier(tier: str | None) -> str:
    mapping = {
        "Tier 1": "High conviction breakout",
        "Tier 2": "Watchlist breakout",
        "Tier 3": "Developing",
    }
    return mapping.get(tier or "", tier or "—")


def friendly_swing_tier(tier: str | None) -> str:
    mapping = {
        "SETUP_LONG": "Pullback long",
        "SETUP_SHORT": "Pullback short",
    }
    return mapping.get(tier or "", tier or "—")


def friendly_swing_grade(label: str | None) -> str:
    if not label:
        return "—"
    text = str(label)
    if text.upper().startswith("A"):
        return "Grade A — strong setup"
    if text.upper().startswith("B"):
        return "Grade B — valid setup"
    return text


def friendly_lynch_categories(categories: list[str] | None) -> str:
    if not categories:
        return "Base screen"
    labels = {
        "fast_grower": "Fast grower",
        "stalwart": "Stalwart",
        "asset_play": "Asset play",
    }
    return ", ".join(labels.get(c, c.replace("_", " ").title()) for c in categories)


def breakout_why(ticker: dict) -> str:
    parts: list[str] = []
    reason = ticker.get("tier_reason")
    if reason:
        parts.append(str(reason))

    insights = signal_insights(ticker)
    for strength in (insights.get("strengths") or [])[:2]:
        if strength not in parts:
            parts.append(strength)

    if not parts:
        scores = ticker.get("scores") or {}
        top = rank_components(scores, n=2)
        for sig in top:
            parts.append(sig.action)

    return truncate(" · ".join(parts) if parts else "Meets actionable breakout thresholds.")


def swing_why(ticker: dict) -> str:
    detail = ticker.get("setup_detail") or {}
    parts: list[str] = []

    note = detail.get("notes") or ticker.get("tier_reason")
    if note:
        parts.append(str(note))

    breakdown = detail.get("rule_breakdown") or []
    passed = sorted(
        [r for r in breakdown if r.get("passed")],
        key=lambda x: float(x.get("score") or 0),
        reverse=True,
    )
    for rule in passed[:3]:
        label = rule.get("label") or rule.get("rule", "")
        if not label:
            continue
        label_str = str(label)
        if any(label_str.lower() in p.lower() or p.lower() in label_str.lower() for p in parts):
            continue
        score = rule.get("score")
        max_pts = rule.get("max")
        if score is not None and max_pts:
            parts.append(f"{label_str} ({float(score):.0f}/{float(max_pts):.0f})")
        else:
            parts.append(label_str)

    rsi = detail.get("rsi")
    if rsi is not None and len(parts) < 4:
        parts.append(f"RSI {float(rsi):.0f}")

    return truncate(" · ".join(parts) if parts else "Weekly pullback into the trend.")


def lynch_why(ticker: dict) -> str:
    summary = ticker.get("investor_summary")
    if summary:
        return truncate(str(summary), max_len=220)
    reason = ticker.get("tier_reason")
    if reason:
        return truncate(str(reason))
    cats = friendly_lynch_categories(ticker.get("categories"))
    peg = format_peg(ticker.get("peg_ratio"))
    return f"Lynch {cats.lower()} candidate · PEG {peg}"


def daily_executive_summary(payload: dict) -> list[str]:
    tier1 = payload.get("tier1") or []
    tier2 = payload.get("tier2") or []
    regime = payload.get("regime") or {}
    label = regime.get("label", "unknown")
    n = len(tier1) + len(tier2)

    if n == 0:
        spy = regime.get("spy_price")
        ret = regime.get("return_63d_pct")
        market = f"Market is {label}"
        if spy is not None:
            market += f" (SPY ${spy}"
            if ret is not None:
                market += f", +{ret}% over 63 days"
            market += ")"
        return [
            f"{market}, but no S&P 500 names met our strict breakout bar today.",
            "Check the weekly digest for swing pullbacks and Lynch value ideas.",
        ]

    lines = [
        f"{n} actionable breakout{'s' if n != 1 else ''} in the S&P 500 ({label} market).",
    ]
    if tier1:
        names = ", ".join(r["ticker"] for r in tier1[:5])
        extra = f" (+{len(tier1) - 5} more)" if len(tier1) > 5 else ""
        lines.append(f"High conviction: {names}{extra}.")
    new = payload.get("new_entrants") or []
    if new:
        lines.append(f"New today: {', '.join(new[:8])}.")
    return lines


def weekly_executive_summary(payload: dict) -> list[str]:
    triple = len(payload.get("triple_alignment") or [])
    swing = len(payload.get("swing_highlights") or [])
    lynch = len(payload.get("lynch_top") or [])
    lines = [
        (
            f"This week: {triple} triple-alignment name{'s' if triple != 1 else ''}, "
            f"{swing} swing pullback{'s' if swing != 1 else ''}, "
            f"{lynch} Lynch value pick{'s' if lynch != 1 else ''}."
        ),
    ]
    if triple:
        names = ", ".join(r["ticker"] for r in payload["triple_alignment"][:5])
        lines.append(f"Best convergence: {names}.")
    elif swing:
        top = payload["swing_highlights"][0]
        lines.append(
            f"Top swing setup: {top['ticker']} ({format_score(top.get('swing_score'))}/100)."
        )
    elif lynch:
        top = payload["lynch_top"][0]
        lines.append(
            f"Top Lynch pick: {top['ticker']} (score {format_score(top.get('lynch_score'))})."
        )
    else:
        lines.append("No standout setups this week — review the dashboard for near-misses.")
    return lines
