"""Actionable appearance rules per strategy (single source of truth)."""

from __future__ import annotations

from typing import Any

ACTIONABLE_TIERS: dict[str, frozenset[str]] = {
    "breakout": frozenset({"Tier 1", "Tier 2"}),
    "launchpad": frozenset({"Tier 1", "Tier 2"}),
    "swing": frozenset({"SETUP_LONG", "SETUP_SHORT"}),
    "lynch": frozenset({"fast_grower", "stalwart", "asset_play", "passed"}),
    "mean_reversion": frozenset({"HIGH_CONVICTION"}),
}

ALL_STRATEGY_IDS = tuple(ACTIONABLE_TIERS.keys())


def is_actionable(
    strategy_id: str,
    *,
    tier: str | None,
    eligible: bool | None = None,
    detail: dict[str, Any] | None = None,
) -> bool:
    """Return True when a ticker row counts as an actionable appearance."""
    if strategy_id == "lynch":
        if detail and detail.get("passed") is True:
            return True
        if eligible is True and tier and tier != "filtered":
            return True
        return tier in ACTIONABLE_TIERS["lynch"] if tier else False

    if not tier:
        return False
    allowed = ACTIONABLE_TIERS.get(strategy_id)
    if not allowed:
        return False
    return tier in allowed


def actionable_sql_clause(*, param_style: str = "%s") -> str:
    """SQL fragment: row is actionable (use with actionable_only=True)."""
    _ = param_style
    return """(
        (sr.strategy_id = 'breakout' AND tr.tier IN ('Tier 1', 'Tier 2'))
        OR (sr.strategy_id = 'launchpad' AND tr.tier IN ('Tier 1', 'Tier 2'))
        OR (sr.strategy_id = 'swing' AND tr.tier IN ('SETUP_LONG', 'SETUP_SHORT'))
        OR (sr.strategy_id = 'mean_reversion' AND tr.tier = 'HIGH_CONVICTION')
        OR (
            sr.strategy_id = 'lynch'
            AND tr.eligible IS TRUE
            AND COALESCE(tr.tier, '') != 'filtered'
        )
    )"""
