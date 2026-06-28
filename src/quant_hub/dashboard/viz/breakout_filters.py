"""Shared breakout dashboard filter helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BreakoutFilters:
    tier: str = "All"
    eligible_only: bool = False
    actionable_only: bool = False
    min_score: float = 0.0
    search: str = ""


def apply_breakout_filters(df: pd.DataFrame, filters: BreakoutFilters) -> pd.DataFrame:
    result = df.copy()
    if filters.tier != "All":
        result = result[result["tier"] == filters.tier]
    if filters.eligible_only:
        result = result[result["eligible"]]
    if filters.actionable_only:
        result = result[result["tier"].isin(["Tier 1", "Tier 2"])]
    if filters.min_score > 0:
        # Tier assignment uses normalized score; final score includes regime discount.
        score_col = (
            "normalized_score"
            if filters.actionable_only and "normalized_score" in result.columns
            else "final_score"
        )
        result = result[result[score_col] >= filters.min_score]
    if filters.search:
        result = result[result["ticker"].str.contains(filters.search, na=False)]
    return result


def scatter_dataframe(tickers: list[dict]) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        if not ticker.get("eligible") or not ticker.get("scores"):
            continue
        rows.append(
            {
                "ticker": ticker["ticker"],
                "tier": ticker["tier"],
                "compression": ticker["scores"]["compression"]["score"],
                "rs_market": ticker["scores"]["rs_market"]["score"],
                "final_score": ticker["summary"]["final_adjusted_score"],
                "normalized_score": ticker["summary"].get("normalized_score"),
            }
        )
    return pd.DataFrame(rows)
