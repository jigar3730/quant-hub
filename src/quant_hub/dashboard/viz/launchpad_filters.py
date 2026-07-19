"""Launchpad dashboard filter helpers."""

from __future__ import annotations

import pandas as pd

from quant_hub.dashboard.viz.breakout_filters import BreakoutFilters, apply_breakout_filters

LaunchpadFilters = BreakoutFilters
apply_launchpad_filters = apply_breakout_filters


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
