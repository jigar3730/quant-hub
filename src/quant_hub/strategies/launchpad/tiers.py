from __future__ import annotations

from quant_hub.config import (
    LAUNCHPAD_TIER1_NORMALIZED_MIN,
    LAUNCHPAD_TIER2_NORMALIZED_MIN,
)
from quant_hub.engine.types import TickerResult
from quant_hub.scoring.launchpad import FILTER_LABELS

MACD_TIER1_SCORE = 25.0


def _tier1_criteria(*, normalized: float, macd_score: float) -> bool:
    return normalized >= LAUNCHPAD_TIER1_NORMALIZED_MIN and macd_score >= MACD_TIER1_SCORE


def assign_tier(ticker: TickerResult) -> str:
    if not ticker.eligible:
        return "filtered"

    normalized = ticker.normalized_score
    macd_score = ticker.factor_score("macd_zero_line")

    if _tier1_criteria(normalized=normalized, macd_score=macd_score):
        return "Tier 1"

    if normalized >= LAUNCHPAD_TIER2_NORMALIZED_MIN:
        return "Tier 2"
    return "Tier 3"


def assign_tier_from_row(row) -> str:
    if not row.get("eligible", False):
        return "filtered"

    normalized = row["normalized_score"]
    macd_score = row.get("macd_zero_line_score", 0) or 0

    if _tier1_criteria(normalized=normalized, macd_score=macd_score):
        return "Tier 1"

    if normalized >= LAUNCHPAD_TIER2_NORMALIZED_MIN:
        return "Tier 2"
    return "Tier 3"


def explain_tier(row: dict) -> str:
    if not row.get("eligible"):
        reason = row.get("filter_reason", "unknown")
        return FILTER_LABELS.get(reason, reason)

    tier = row.get("tier", "")
    normalized = row.get("normalized_score", 0)
    macd_score = row.get("macd_zero_line_score", 0)
    t2_min = LAUNCHPAD_TIER2_NORMALIZED_MIN
    t1_min = LAUNCHPAD_TIER1_NORMALIZED_MIN

    if tier == "Tier 1":
        return (
            f"Perfect launchpad: score {normalized:.1f} (>={t1_min:.0f}) "
            f"with MACD zero-line ignition ({macd_score:.0f} pts)"
        )

    if tier == "Tier 2":
        if normalized >= LAUNCHPAD_TIER1_NORMALIZED_MIN and macd_score < MACD_TIER1_SCORE:
            return (
                f"Watchlist: score {normalized:.1f} (>={t2_min:.0f}) "
                f"but MACD zero-line not active ({macd_score:.0f} < {MACD_TIER1_SCORE:.0f} pts)"
            )
        return f"Watchlist: normalized score {normalized:.1f} (>={t2_min:.0f})"

    return f"Below watchlist threshold: normalized score {normalized:.1f} (<{t2_min:.0f})"
