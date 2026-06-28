"""Swing dashboard filter helpers."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SwingFilters:
    setup_type: str = "All"
    min_rsi: float = 0.0
    search: str = ""


def swing_setups_dataframe(tickers: list[dict]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        detail = t.get("setup_detail") or {}
        summary = t.get("summary") or {}
        scores = t.get("scores") or {}
        rows.append(
            {
                "ticker": t["ticker"],
                "setup_type": t.get("tier"),
                "close": detail.get("close"),
                "rsi": summary.get("final_adjusted_score"),
                "ema20": (scores.get("ema20") or {}).get("score"),
                "ema50": (scores.get("ema50") or {}).get("score"),
                "atr": (scores.get("atr") or {}).get("score"),
                "notes": t.get("tier_reason", ""),
            }
        )
    return pd.DataFrame(rows).sort_values("rsi", ascending=False)


def apply_swing_filters(df: pd.DataFrame, filters: SwingFilters) -> pd.DataFrame:
    result = df.copy()
    if filters.setup_type != "All":
        result = result[result["setup_type"] == filters.setup_type]
    if filters.min_rsi > 0:
        result = result[result["rsi"] >= filters.min_rsi]
    if filters.search:
        result = result[result["ticker"].str.contains(filters.search, na=False)]
    return result
