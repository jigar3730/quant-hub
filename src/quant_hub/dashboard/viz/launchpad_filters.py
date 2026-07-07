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
                "macd_zero_line": scores["macd_zero_line"]["score"],
                "ma_tightness": scores["ma_tightness"]["score"],
                "final_score": ticker["summary"]["final_adjusted_score"],
                "normalized_score": ticker["summary"].get("normalized_score"),
            }
        )
    return pd.DataFrame(rows)
