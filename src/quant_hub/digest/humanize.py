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


# Factor order controls display priority (highest max points first).
_FACTOR_DISPLAY_ORDER = (
    "squeeze_intensity",
    "volume_vacuum_depth",
    "macd_zero_line",
    "tightness_percentile",
    "trend_proximity_match",
)


def launchpad_factor_highlights(ticker: dict[str, Any]) -> list[str]:
    """Human-readable factor signals that contributed to this ticker's score."""
    scores = ticker.get("scores") or {}
    highlights = []
    for factor in _FACTOR_DISPLAY_ORDER:
        detail = scores.get(factor) or {}
        score = detail.get("score") or 0
        meaning = detail.get("meaning")
        if score > 0 and meaning:
            highlights.append(str(meaning))
    return highlights


def launchpad_setup_text(ticker: dict[str, Any]) -> str:
    """One-sentence description of the setup to watch, built from already-computed levels."""
    scores = ticker.get("scores") or {}
    trend_raw = (scores.get("trend_proximity_match") or {}).get("raw") or {}
    squeeze_raw = (scores.get("squeeze_intensity") or {}).get("raw") or {}
    volume_raw = (scores.get("volume_vacuum_depth") or {}).get("raw") or {}

    ema50 = trend_raw.get("price_ema50")
    parts: list[str] = []
    if ema50 is not None:
        parts.append(f"Watch for a breakout above EMA50 (${ema50:.2f})")
    else:
        parts.append("Watch for a breakout on expanding volume")

    rvol = volume_raw.get("rvol")
    if rvol is not None:
        parts[-1] += f" on expanding volume (RVOL {rvol})"

    proximity_bits = []
    atr_distance = trend_raw.get("atr_distance")
    grade = trend_raw.get("near_support_grade")
    if atr_distance is not None:
        proximity_bits.append(f"{atr_distance} ATR from support" + (f" (grade: {grade})" if grade else ""))
    squeeze_ratio = squeeze_raw.get("squeeze_ratio")
    if squeeze_ratio is not None:
        proximity_bits.append(f"squeeze ratio {squeeze_ratio}")

    sentence = parts[0] + "."
    if proximity_bits:
        sentence += f" Currently {', '.join(proximity_bits)}."
    return sentence


def launchpad_near_miss_why(ticker: dict[str, Any]) -> str:
    """Why a Tier 3 ticker didn't qualify — reuses the persisted tier_reason explanation."""
    return launchpad_why(ticker)


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
    universes = payload.get("universes") or []
    regime = payload.get("regime") or {}
    label = regime.get("label", "unknown")

    all_tier1 = [row for u in universes for row in (u.get("tier1") or [])]
    all_tier2 = [row for u in universes for row in (u.get("tier2") or [])]
    total = len(all_tier1) + len(all_tier2)
    total_near_miss = sum(len(u.get("near_misses") or []) for u in universes)

    if not universes:
        return ["No Launchpad scans available today."]

    if not total:
        lines = [
            f"No actionable Launchpad names across {len(universes)} screened universes ({label} market)."
        ]
        if total_near_miss:
            lines.append(f'{total_near_miss} names came close today — see "Closest to qualifying" below.')
        else:
            lines.append("Review the weekly Lynch digest for fundamentally screened candidates.")
        return lines

    noun = "name" if total == 1 else "names"
    lines = [f"{total} actionable Launchpad {noun} across {len(universes)} universes ({label} market)."]
    if all_tier1:
        names = ", ".join(row["ticker"] for row in all_tier1[:5])
        suffix = f" (+{len(all_tier1) - 5} more)" if len(all_tier1) > 5 else ""
        lines.append(f"High conviction: {names}{suffix}.")
    breakdown = ", ".join(
        f"{u['universe_label']} {len(u.get('tier1') or []) + len(u.get('tier2') or [])}"
        for u in universes
    )
    lines.append(f"By universe: {breakdown}.")
    new_entrants = sorted({ticker for u in universes for ticker in (u.get("new_entrants") or [])})
    if new_entrants:
        lines.append(f"New today: {', '.join(new_entrants[:8])}.")
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
