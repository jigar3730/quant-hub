"""Plain-language helpers for Launchpad and Lynch digests."""

from __future__ import annotations

from typing import Any


def truncate(text: str, *, max_len: int = 180) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= max_len else text[: max_len - 1].rstrip() + "…"


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
        peg = float(value)
        return "neg earnings" if peg < 0 else f"{peg:.2f}"
    except (TypeError, ValueError):
        return str(value)


def friendly_launchpad_tier(tier: str | None) -> str:
    return {
        "Tier 1": "High-conviction Launchpad",
        "Tier 2": "Launchpad watchlist",
        "Tier 3": "Developing",
    }.get(tier or "", tier or "—")


def friendly_lynch_categories(categories: list[str] | None) -> str:
    if not categories:
        return "Base screen"
    labels = {
        "fast_grower": "Fast grower",
        "stalwart": "Stalwart",
        "asset_play": "Asset play",
    }
    return ", ".join(labels.get(category, category.replace("_", " ").title()) for category in categories)


def launchpad_why(ticker: dict[str, Any]) -> str:
    reason = ticker.get("tier_reason")
    if reason:
        return truncate(str(reason))
    summary = ticker.get("summary") or {}
    score = summary.get("normalized_score", ticker.get("normalized_score"))
    if score is not None:
        return f"Qualified Launchpad with normalized score {format_score(score)}."
    return "Qualified Launchpad setup."


def lynch_why(ticker: dict[str, Any]) -> str:
    summary = ticker.get("investor_summary")
    if summary:
        return truncate(str(summary), max_len=220)
    reason = ticker.get("tier_reason")
    if reason:
        return truncate(str(reason))
    categories = friendly_lynch_categories(ticker.get("categories"))
    return f"Lynch {categories.lower()} candidate · PEG {format_peg(ticker.get('peg_ratio'))}"


def daily_executive_summary(payload: dict[str, Any]) -> list[str]:
    tier1 = payload.get("tier1") or []
    tier2 = payload.get("tier2") or []
    regime = payload.get("regime") or {}
    label = regime.get("label", "unknown")
    count = len(tier1) + len(tier2)
    if not count:
        return [
            f"The S&P 500 Launchpad scan found no actionable names in a {label} market.",
            "Review the weekly Lynch digest for fundamentally screened candidates.",
        ]
    noun = "name" if count == 1 else "names"
    lines = [f"{count} actionable Launchpad {noun} in the S&P 500 ({label} market)."]
    if tier1:
        names = ", ".join(row["ticker"] for row in tier1[:5])
        suffix = f" (+{len(tier1) - 5} more)" if len(tier1) > 5 else ""
        lines.append(f"High conviction: {names}{suffix}.")
    if payload.get("new_entrants"):
        lines.append(f"New today: {', '.join(payload['new_entrants'][:8])}.")
    return lines


def weekly_executive_summary(payload: dict[str, Any]) -> list[str]:
    lynch = payload.get("lynch_top") or []
    overlap = payload.get("launchpad_overlap") or []
    lines = [
        f"This week: {len(lynch)} Lynch candidate{'s' if len(lynch) != 1 else ''}"
        f" and {len(overlap)} Launchpad overlap{'s' if len(overlap) != 1 else ''}.",
    ]
    if overlap:
        lines.append(f"Cross-screen names: {', '.join(row['ticker'] for row in overlap[:5])}.")
    elif lynch:
        top = lynch[0]
        lines.append(f"Top Lynch candidate: {top['ticker']} (score {format_score(top.get('lynch_score'))}).")
    else:
        lines.append("No Lynch candidates passed this week's screen.")
    return lines
