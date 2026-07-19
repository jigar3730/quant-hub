"""Launchpad score component diagnostics for reports."""

from __future__ import annotations

import pandas as pd

from quant_hub.scoring.launchpad import (
    score_macd_zero_line,
    score_squeeze_intensity,
    score_tightness_percentile,
    score_volume_vacuum_depth,
    score_trend_proximity_match,
)


def launchpad_score_components_detail(
    *,
    stock_df: pd.DataFrame,
    scores: dict,
    spy_df: pd.DataFrame | None = None,
) -> dict:
    squeeze_score, squeeze_raw = score_squeeze_intensity(stock_df)
    tightness_score, tightness_raw = score_tightness_percentile(stock_df)
    volume_score, volume_raw = score_volume_vacuum_depth(stock_df)
    macd_score, macd_raw = score_macd_zero_line(stock_df)
    # Prefer real SPY; never pass stock_df as its own benchmark.
    bench = spy_df if spy_df is not None and not spy_df.empty else None
    if bench is not None:
        trend_score, trend_raw = score_trend_proximity_match(stock_df, bench)
    else:
        trend_score, trend_raw = 0.0, {"error": "missing_spy"}

    return {
        "macd_zero_line": {
            "score": scores.get("macd_zero_line_score", macd_score),
            "max": 25,
            "raw": macd_raw,
            "meaning": _macd_meaning(macd_score, macd_raw),
        },
        "squeeze_intensity": {
            "score": scores.get("squeeze_intensity_score", squeeze_score),
            "max": 40,
            "raw": squeeze_raw,
            "meaning": _squeeze_meaning(squeeze_score, squeeze_raw),
        },
        "tightness_percentile": {
            "score": scores.get("tightness_percentile_score", tightness_score),
            "max": 15,
            "raw": tightness_raw,
            "meaning": _tightness_meaning(tightness_score, tightness_raw),
        },
        "volume_vacuum_depth": {
            "score": scores.get("volume_vacuum_depth_score", volume_score),
            "max": 30,
            "raw": volume_raw,
            "meaning": _volume_meaning(volume_score, volume_raw),
        },
        "trend_proximity_match": {
            "score": scores.get("trend_proximity_match_score", trend_score),
            "max": 15,
            "raw": trend_raw,
            "meaning": _trend_meaning(
                scores.get("trend_proximity_match_score", trend_score),
                trend_raw,
            ),
        },
    }


def _macd_meaning(score: float, raw: dict) -> str:
    phase = raw.get("phase")
    if score >= 25:
        return "MACD zero-line ignition (line + signal crossed above zero)"
    if score >= 15:
        return f"MACD early recovery ({phase})"
    return f"MACD not igniting ({phase or 'inactive'})"


def _squeeze_meaning(score: float, raw: dict) -> str:
    ratio = raw.get("squeeze_ratio")
    if score >= 40:
        return f"Extreme squeeze compression (ratio {ratio} < 0.90)"
    if score >= 25:
        return f"Standard squeeze compression (ratio {ratio} <= 1.00)"
    return f"No clear squeeze (ratio {ratio})"


def _tightness_meaning(score: float, raw: dict) -> str:
    rank = raw.get("tightness_rank_pct")
    if score >= 15:
        return f"Candle tightness in lowest 10th percentile ({rank:.0%})"
    if rank is None:
        return "Candle tightness unavailable"
    return f"Candle ranges not yet compressed ({rank:.0%})"


def _volume_meaning(score: float, raw: dict) -> str:
    ratio = raw.get("rvol")
    if score >= 30:
        return f"Complete volume vacuum (RVOL {ratio})"
    if score >= 15:
        return f"Moderately dry volume (RVOL {ratio})"
    return f"Volume still active (RVOL {ratio})"


def _trend_meaning(score: float, raw: dict) -> str:
    if raw.get("error"):
        return "Trend/proximity unavailable (missing SPY)"
    rs = raw.get("rs_score", 0)
    near = raw.get("near_support_score", 0)
    grade = raw.get("near_support_grade", "none")
    if score >= 15:
        return "Full RS vs SPY and tight proximity to support"
    if score > 0:
        return f"Partial trend/proximity (RS {rs:.0f} + near-support {near:.0f}, grade={grade})"
    return "Trend/proximity match not yet satisfied"
