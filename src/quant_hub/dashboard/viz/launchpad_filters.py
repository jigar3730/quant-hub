"""Launchpad dashboard filter helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class LaunchpadFilters:
    """Sidebar filters applied to Launchpad scan tables."""

    tier: str = "All"
    eligible_only: bool = False
    actionable_only: bool = False
    min_score: float = 0.0
    search: str = ""


def apply_launchpad_filters(df: pd.DataFrame, filters: LaunchpadFilters) -> pd.DataFrame:
    """Return rows matching the selected Launchpad tiers, score, and ticker search."""
    result = df.copy()
    if filters.tier != "All":
        result = result[result["tier"] == filters.tier]
    if filters.eligible_only:
        result = result[result["eligible"]]
    if filters.actionable_only:
        result = result[result["tier"].isin(["Tier 1", "Tier 2"])]
    if filters.min_score > 0:
        result = result[result["normalized_score"] >= filters.min_score]
    if filters.search:
        result = result[result["ticker"].str.contains(filters.search, case=False, na=False)]
    return result


def launchpad_scatter_dataframe(tickers: list[dict]) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        if not ticker.get("eligible") or not ticker.get("scores"):
            continue
        scores = ticker["scores"]
        rows.append(
            {
                "ticker": ticker["ticker"],
                "tier": ticker["tier"],
                "squeeze_intensity": scores.get("squeeze_intensity", {}).get("score", 0),
                "tightness_percentile": scores.get("tightness_percentile", {}).get("score", 0),
                "final_score": ticker["summary"].get("final_adjusted_score", 0),
                "normalized_score": ticker["summary"].get("normalized_score"),
            }
        )
    return pd.DataFrame(rows)
