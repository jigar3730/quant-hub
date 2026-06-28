from __future__ import annotations

from quant_hub.engine.types import TickerResult
from quant_hub.filters.eligibility import FILTER_LABELS


def assign_tier(ticker: TickerResult) -> str:
    if not ticker.eligible:
        return "filtered"

    normalized = ticker.normalized_score
    final = ticker.final_score
    compression = ticker.factor_score("compression")
    accumulation = ticker.factor_score("accumulation")
    rel_vol = ticker.factor_score("relative_volume")

    tier1 = (
        normalized >= 80
        and final >= 70
        and compression >= 8
        and (accumulation >= 8 or rel_vol >= 5)
    )
    if tier1:
        return "Tier 1"

    if normalized >= 65:
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

    tier1 = (
        normalized >= 80
        and final >= 70
        and compression >= 8
        and (accumulation >= 8 or rel_vol >= 5)
    )
    if tier1:
        return "Tier 1"

    if normalized >= 65:
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

    if tier == "Tier 1":
        return (
            f"Breakout ready: score {normalized:.1f} (>=80), adjusted {final:.1f} (>=70), "
            f"compression {compression:.1f} (>=8), volume signal met"
        )

    if tier == "Tier 2":
        if normalized >= 80:
            missing = []
            if final < 70:
                missing.append(f"adjusted score {final:.1f} < 70")
            if compression < 8:
                missing.append(f"compression {compression:.1f} < 8")
            if accumulation < 8 and rel_vol < 5:
                missing.append("accumulation and relative volume below Tier 1 thresholds")
            joined = "; ".join(missing)
            return f"High score ({normalized:.1f}) but missing Tier 1 criteria: {joined}"
        return f"Watchlist candidate: normalized score {normalized:.1f} (65-79 range)"

    return f"Below watchlist threshold: normalized score {normalized:.1f} (<65)"
