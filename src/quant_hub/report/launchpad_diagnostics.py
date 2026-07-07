"""Launchpad Reversal score component diagnostics for reports."""

from __future__ import annotations

import pandas as pd

from quant_hub.scoring.launchpad import (
    score_atr_contraction,
    score_ma_tightness,
    score_macd_zero_line,
    score_swing_low_vcp,
    score_volume_dry_up,
)


def launchpad_score_components_detail(
    *,
    stock_df: pd.DataFrame,
    scores: dict,
) -> dict:
    ma_score, ma_raw = score_ma_tightness(stock_df)
    macd_score, macd_raw = score_macd_zero_line(stock_df)
    atr_score, atr_raw = score_atr_contraction(stock_df)
    vol_score, vol_raw = score_volume_dry_up(stock_df)
    vcp_score, vcp_raw = score_swing_low_vcp(stock_df)

    return {
        "ma_tightness": {
            "score": scores.get("ma_tightness_score", ma_score),
            "max": 25,
            "raw": ma_raw,
            "meaning": _ma_meaning(ma_score, ma_raw),
        },
        "macd_zero_line": {
            "score": scores.get("macd_zero_line_score", macd_score),
            "max": 25,
            "raw": macd_raw,
            "meaning": _macd_meaning(macd_score),
        },
        "atr_contraction": {
            "score": scores.get("atr_contraction_score", atr_score),
            "max": 20,
            "raw": atr_raw,
            "meaning": _atr_meaning(atr_score, atr_raw),
        },
        "volume_dry_up": {
            "score": scores.get("volume_dry_up_score", vol_score),
            "max": 15,
            "raw": vol_raw,
            "meaning": _volume_meaning(vol_score, vol_raw),
        },
        "swing_low_vcp": {
            "score": scores.get("swing_low_vcp_score", vcp_score),
            "max": 15,
            "raw": vcp_raw,
            "meaning": _vcp_meaning(vcp_score, vcp_raw),
        },
    }


def _macd_meaning(score: float) -> str:
    if score >= 25:
        return "MACD zero-line ignition active (bullish crossover above zero)"
    if score >= 15:
        return "Early MACD recovery (above signal, still below zero)"
    return "MACD below signal or no momentum confirmation"


def _ma_meaning(score: float, raw: dict) -> str:
    spread = raw.get("ma_spread_pct")
    if score >= 25:
        return f"Maximum MA coil (spread {spread}% <= 3%)"
    if score >= 15:
        return f"Moderate MA squeeze (spread {spread}% <= 6%)"
    if spread is not None:
        return f"MAs fanned out (spread {spread}% > 6%)"
    return "MA tightness not computable"


def _atr_meaning(score: float, raw: dict) -> str:
    ratio = raw.get("volatility_ratio")
    if score >= 20:
        return f"Strong range contraction (ATR ratio {ratio} < 0.70)"
    if score >= 12:
        return f"Moderate range contraction (ATR ratio {ratio} < 0.80)"
    if ratio is not None:
        return f"No range contraction (ATR ratio {ratio} >= 0.80)"
    return "ATR contraction not computable"


def _volume_meaning(score: float, raw: dict) -> str:
    ratio = raw.get("volume_dry_up_ratio")
    if score >= 15:
        return f"Volume fully dried up ({ratio}× 50-day baseline, sellers exhausted)"
    if score >= 10:
        return f"Volume drying up ({ratio}× 50-day baseline)"
    if ratio is not None:
        return f"Volume still active ({ratio}× 50-day baseline)"
    return "Volume dry-up not computable"


def _vcp_meaning(score: float, raw: dict) -> str:
    ratio = raw.get("contraction_ratio")
    if score >= 15:
        return f"Textbook VCP contraction (latest pullback {ratio}× the prior)"
    if score >= 8:
        return f"Partial VCP contraction (latest pullback {ratio}× the prior)"
    count = raw.get("pullback_leg_count", 0)
    if count < 2:
        return "Insufficient pullback structure for VCP"
    return "Pullbacks not contracting (latest deeper than prior)"
