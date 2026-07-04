"""Mean reversion rubric v2.2 scoring (0–100)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from quant_hub.strategies.mean_reversion.constants import (
    HIGH_CONVICTION_THRESHOLD,
    MACRO_TREND_POINTS,
    MAX_SCORE,
    PRICE_EXTENSION_POINTS,
    RSI_HOOK_POINTS,
    SECTOR_ROTATION_POINTS,
    SETUP_LONG,
    SETUP_SHORT,
    SIGNAL_MARGINAL,
    SIGNAL_NO_TRADE,
    SIGNAL_STRONG_LONG,
    SIGNAL_STRONG_SHORT,
    TIER_FILTERED,
    TIER_HIGH_CONVICTION,
    TIER_WATCHLIST,
    VOLATILITY_POINTS,
    VOLUME_POINTS,
    WATCHLIST_THRESHOLD,
)
from quant_hub.strategies.mean_reversion.metrics import (
    at_band_zone,
    bb_width_percentile,
    macro_trend_points,
    price_extension_points,
    rsi_hook_state,
    sector_rotation_points,
    volatility_regime_points,
    volume_confirmation_points,
)


@dataclass(frozen=True)
class SideScore:
    side: str
    total_score: float
    rule_breakdown: list[dict]
    setup_type: str


@dataclass(frozen=True)
class MeanReversionScoreResult:
    total_score: float
    scored_side: str
    setup_type: str
    signal: str
    tier: str
    rule_breakdown: list[dict]
    long_score: float
    short_score: float


def _rule_row(
    rule: str,
    label: str,
    points: float,
    *,
    max_points: float,
    passed: bool,
    detail: str = "",
) -> dict:
    return {
        "rule": rule,
        "label": label,
        "score": round(points, 1),
        "max": max_points,
        "passed": passed,
        "detail": detail,
    }


def _score_side(
    df: pd.DataFrame,
    *,
    side: str,
    close: float,
    ema500: float,
    upper: float,
    mid: float,
    lower: float,
    rs_percentile: float | None,
) -> SideScore:
    rsi_series = df["RSI"]
    width_pct = bb_width_percentile(df)

    macro_pts, macro_detail = macro_trend_points(
        close, ema500, side=side, max_pts=float(MACRO_TREND_POINTS)
    )
    ext_pts, ext_detail = price_extension_points(
        close, side=side, upper=upper, lower=lower, max_pts=float(PRICE_EXTENSION_POINTS)
    )

    at_zone = at_band_zone(close, side=side, upper=upper, lower=lower)
    if at_zone:
        rsi_pts, rsi_detail = rsi_hook_state(rsi_series, side=side)
    else:
        rsi_pts, rsi_detail = 0.0, "not_at_band"

    vol_pts, vol_detail = volume_confirmation_points(df, float(VOLUME_POINTS))
    sector_pts, sector_detail = sector_rotation_points(
        rs_percentile, side=side, max_pts=float(SECTOR_ROTATION_POINTS)
    )
    vreg_pts, vreg_detail = volatility_regime_points(width_pct, float(VOLATILITY_POINTS))

    breakdown = [
        _rule_row(
            f"{side}_macro_trend",
            "Macro Trend (500 EMA)",
            macro_pts,
            max_points=float(MACRO_TREND_POINTS),
            passed=macro_pts >= MACRO_TREND_POINTS * 0.5,
            detail=macro_detail,
        ),
        _rule_row(
            f"{side}_price_extension",
            "Price Extension (Bollinger)",
            ext_pts,
            max_points=float(PRICE_EXTENSION_POINTS),
            passed=ext_pts >= PRICE_EXTENSION_POINTS * 0.5,
            detail=ext_detail,
        ),
        _rule_row(
            f"{side}_rsi_hook",
            "RSI Momentum Hook",
            rsi_pts,
            max_points=float(RSI_HOOK_POINTS),
            passed=rsi_pts >= 8,
            detail=rsi_detail,
        ),
        _rule_row(
            f"{side}_volume",
            "Volume Confirmation",
            vol_pts,
            max_points=float(VOLUME_POINTS),
            passed=vol_pts >= VOLUME_POINTS * 0.4,
            detail=vol_detail,
        ),
        _rule_row(
            f"{side}_sector_rotation",
            "Sector Rotation",
            sector_pts,
            max_points=float(SECTOR_ROTATION_POINTS),
            passed=sector_pts >= SECTOR_ROTATION_POINTS * 0.5,
            detail=sector_detail,
        ),
        _rule_row(
            f"{side}_volatility",
            "Volatility Regime",
            vreg_pts,
            max_points=float(VOLATILITY_POINTS),
            passed=vreg_pts >= VOLATILITY_POINTS * 0.5,
            detail=vreg_detail,
        ),
    ]

    total = round(min(sum(r["score"] for r in breakdown), MAX_SCORE), 1)
    setup_type = SETUP_LONG if side == "long" else SETUP_SHORT
    return SideScore(
        side=side,
        total_score=total,
        rule_breakdown=breakdown,
        setup_type=setup_type,
    )


def _signal_and_tier(score: float, side: str) -> tuple[str, str]:
    if score > HIGH_CONVICTION_THRESHOLD:
        signal = SIGNAL_STRONG_LONG if side == "long" else SIGNAL_STRONG_SHORT
        return signal, TIER_HIGH_CONVICTION
    if score >= WATCHLIST_THRESHOLD:
        return SIGNAL_MARGINAL, TIER_WATCHLIST
    return SIGNAL_NO_TRADE, TIER_FILTERED


def score_mean_reversion(
    df: pd.DataFrame,
    *,
    rs_percentile: float | None = None,
) -> MeanReversionScoreResult:
    """Score both long and short; winning side becomes bias."""
    latest = df.iloc[-1]
    close = float(latest["Close"])
    ema500 = float(latest["EMA500"])
    upper = float(latest["BB_Upper"])
    mid = float(latest["BB_Mid"])
    lower = float(latest["BB_Lower"])

    long_side = _score_side(
        df,
        side="long",
        close=close,
        ema500=ema500,
        upper=upper,
        mid=mid,
        lower=lower,
        rs_percentile=rs_percentile,
    )
    short_side = _score_side(
        df,
        side="short",
        close=close,
        ema500=ema500,
        upper=upper,
        mid=mid,
        lower=lower,
        rs_percentile=rs_percentile,
    )

    if long_side.total_score >= short_side.total_score:
        winner = long_side
    else:
        winner = short_side

    signal, tier = _signal_and_tier(winner.total_score, winner.side)

    return MeanReversionScoreResult(
        total_score=winner.total_score,
        scored_side=winner.side,
        setup_type=winner.setup_type,
        signal=signal,
        tier=tier,
        rule_breakdown=winner.rule_breakdown,
        long_score=long_side.total_score,
        short_score=short_side.total_score,
    )


def score_from_analysis(analysis: Any) -> MeanReversionScoreResult:
    cached = getattr(analysis, "score_result", None)
    if cached is not None:
        return cached
    raise ValueError("analysis has no score_result attached")
