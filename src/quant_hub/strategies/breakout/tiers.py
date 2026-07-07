from __future__ import annotations

from quant_hub.config import (
    BREAKOUT_TIER1_ACCUMULATION_MIN,
    BREAKOUT_TIER1_COMPRESSION_MIN,
    BREAKOUT_TIER1_FINAL_MIN,
    BREAKOUT_TIER1_NORMALIZED_MIN,
    BREAKOUT_TIER1_REL_VOLUME_MIN,
    BREAKOUT_TIER2_NORMALIZED_MIN,
)
from quant_hub.engine.types import TickerResult
from quant_hub.filters.eligibility import FILTER_LABELS


def _tier1_criteria(
    *,
    normalized: float,
    final: float,
    compression: float,
    accumulation: float,
    rel_vol: float,
) -> bool:
    return (
        normalized >= BREAKOUT_TIER1_NORMALIZED_MIN
        and final >= BREAKOUT_TIER1_FINAL_MIN
        and compression >= BREAKOUT_TIER1_COMPRESSION_MIN
        and (
            accumulation >= BREAKOUT_TIER1_ACCUMULATION_MIN
            or rel_vol >= BREAKOUT_TIER1_REL_VOLUME_MIN
        )
    )


def assign_tier(ticker: TickerResult) -> str:
    if not ticker.eligible:
        return "filtered"

    normalized = ticker.normalized_score
    final = ticker.final_score
    compression = ticker.factor_score("compression")
    accumulation = ticker.factor_score("accumulation")
    rel_vol = ticker.factor_score("relative_volume")

    if _tier1_criteria(
        normalized=normalized,
        final=final,
        compression=compression,
        accumulation=accumulation,
        rel_vol=rel_vol,
    ):
        return "Tier 1"

    if normalized >= BREAKOUT_TIER2_NORMALIZED_MIN:
        return "Tier 2"
    return "Tier 3"


def assign_tier_from_row(row) -> str:
    """Legacy adapter for pandas Series / dict rows."""
    if not row.get("eligible", False):
        return "filtered"

    normalized = row["normalized_score"]
    final = row["final_adjusted_score"]
    compression = row["compression_score"]
    accumulation = row["accumulation_score"]
    rel_vol = row["relative_volume_score"]

    if _tier1_criteria(
        normalized=normalized,
        final=final,
        compression=compression,
        accumulation=accumulation,
        rel_vol=rel_vol,
    ):
        return "Tier 1"

    if normalized >= BREAKOUT_TIER2_NORMALIZED_MIN:
        return "Tier 2"
    return "Tier 3"


def explain_tier(row: dict) -> str:
    if not row.get("eligible"):
        reason = row.get("filter_reason", "unknown")
        return FILTER_LABELS.get(reason, reason)

    tier = row.get("tier", "")
    normalized = row.get("normalized_score", 0)
    final = row.get("final_adjusted_score", 0)
    compression = row.get("compression_score", 0)
    accumulation = row.get("accumulation_score", 0)
    rel_vol = row.get("relative_volume_score", 0)
    t2_min = BREAKOUT_TIER2_NORMALIZED_MIN
    t1_norm = BREAKOUT_TIER1_NORMALIZED_MIN
    t1_final = BREAKOUT_TIER1_FINAL_MIN
    t1_comp = BREAKOUT_TIER1_COMPRESSION_MIN
    t1_acc = BREAKOUT_TIER1_ACCUMULATION_MIN
    t1_rvol = BREAKOUT_TIER1_REL_VOLUME_MIN

    if tier == "Tier 1":
        return (
            f"Breakout ready: score {normalized:.1f} (>={t1_norm:.0f}), "
            f"adjusted {final:.1f} (>={t1_final:.0f}), "
            f"compression {compression:.1f} (>={t1_comp:.0f}), "
            f"volume signal met (accumulation >={t1_acc:.0f} or "
            f"relative volume >={t1_rvol:.0f} pts, ~1.5× avg volume)"
        )

    if tier == "Tier 2":
        if normalized >= BREAKOUT_TIER1_NORMALIZED_MIN:
            missing = []
            if final < BREAKOUT_TIER1_FINAL_MIN:
                missing.append(f"adjusted score {final:.1f} < {t1_final:.0f}")
            if compression < BREAKOUT_TIER1_COMPRESSION_MIN:
                missing.append(f"compression {compression:.1f} < {t1_comp:.0f}")
            if (
                accumulation < BREAKOUT_TIER1_ACCUMULATION_MIN
                and rel_vol < BREAKOUT_TIER1_REL_VOLUME_MIN
            ):
                missing.append(
                    f"accumulation < {t1_acc:.0f} and relative volume < {t1_rvol:.0f} pts "
                    "(need ≥5 pts ≈1.5× avg volume)"
                )
            joined = "; ".join(missing)
            return f"High score ({normalized:.1f}) but missing Tier 1 criteria: {joined}"
        return (
            f"Watchlist candidate: normalized score {normalized:.1f} "
            f"({t2_min:.0f}-{t1_norm - 0.1:.0f} range)"
        )

    return f"Below watchlist threshold: normalized score {normalized:.1f} (<{t2_min:.0f})"
