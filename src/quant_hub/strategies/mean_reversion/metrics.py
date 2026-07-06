"""Mean reversion metric helpers — rubric v2.2 per spec."""

from __future__ import annotations

import pandas as pd

from quant_hub.indicators import bollinger_width


def band_width(upper: float, lower: float) -> float:
    return max(upper - lower, 1e-9)


def extension_distance_pct(
    close: float,
    band: float,
    *,
    side: str,
    upper: float,
    lower: float,
) -> float:
    """Distance from close to target band as fraction of band width (0 = at band)."""
    width = band_width(upper, lower)
    if side == "long":
        if close <= lower:
            return 0.0
        return (close - lower) / width
    if close >= upper:
        return 0.0
    return (upper - close) / width


def at_band_zone(
    close: float,
    *,
    side: str,
    upper: float,
    lower: float,
    max_distance_pct: float = 0.5,
) -> bool:
    """RSI hook zone: at/past band or within 50% of band width."""
    return extension_distance_pct(
        close, lower if side == "long" else upper, side=side, upper=upper, lower=lower
    ) <= max_distance_pct


def bb_width_percentile(df: pd.DataFrame, lookback: int = 120) -> float | None:
    close = df["Close"]
    width = bollinger_width(close, 20).dropna()
    if len(width) < lookback:
        return None
    history = width.tail(lookback)
    today = float(history.iloc[-1])
    return float((history <= today).mean())


def rsi_hook_state(rsi: pd.Series, *, side: str) -> tuple[float, str]:
    """
    RSI Momentum Hook (25 pts) — zone + direction per spec.

    Long: at lower BB — cross from oversold, hook forming, or RSI 30–40 rising.
    Short: mirror at upper BB vs overbought.
    """
    if len(rsi) < 4:
        return 0.0, "insufficient_rsi"

    r0 = float(rsi.iloc[-1])
    r1 = float(rsi.iloc[-2])
    r2 = float(rsi.iloc[-3])
    rising = r0 > r1
    falling = r0 < r1

    if side == "long":
        recent_oversold = any(float(rsi.iloc[i]) < 30 for i in range(-4, 0))
        if recent_oversold and r0 > 30 and rising:
            return 25.0, "cross_from_oversold"
        if r0 < 30 and rising and r1 > r2:
            return 15.0, "hook_forming_oversold"
        if 30 <= r0 <= 40 and rising:
            return 8.0, "rsi_30_40_rising"
        return 0.0, "no_long_hook"

    recent_overbought = any(float(rsi.iloc[i]) > 70 for i in range(-4, 0))
    if recent_overbought and r0 < 70 and falling:
        return 25.0, "cross_from_overbought"
    if r0 > 70 and falling and r1 < r2:
        return 15.0, "hook_forming_overbought"
    if 60 <= r0 <= 70 and falling:
        return 8.0, "rsi_60_70_falling"
    return 0.0, "no_short_hook"


def macro_trend_points(close: float, ema500: float, *, side: str, max_pts: float) -> tuple[float, str]:
    """Macro Trend (20 pts): Price > 500 EMA (Long) or < 500 EMA (Short)."""
    if ema500 <= 0:
        return 0.0, "invalid_ema500"
    if side == "long":
        if close > ema500:
            return max_pts, "above_ema500"
        pct_below = (ema500 - close) / ema500 * 100
        if pct_below <= 1.0:
            return max_pts * 0.5, "within_1pct_below_ema500"
        return 0.0, "below_ema500"
    if close < ema500:
        return max_pts, "below_ema500"
    pct_above = (close - ema500) / ema500 * 100
    if pct_above <= 1.0:
        return max_pts * 0.5, "within_1pct_above_ema500"
    return 0.0, "above_ema500"


def price_extension_points(
    close: float,
    *,
    side: str,
    upper: float,
    lower: float,
    max_pts: float,
) -> tuple[float, str]:
    """Price Extension (30 pts): near/at lower BB (long) or upper BB (short)."""
    dist = extension_distance_pct(
        close, lower if side == "long" else upper, side=side, upper=upper, lower=lower
    )
    if dist <= 0:
        return max_pts, "at_or_past_band"
    if dist <= 0.25:
        return max_pts * (2 / 3), "within_25pct_band_width"
    if dist <= 0.50:
        return max_pts * (1 / 3), "within_50pct_band_width"
    return 0.0, "not_extended"


def volume_confirmation_points(df: pd.DataFrame, max_pts: float) -> tuple[float, str]:
    from quant_hub.scoring.volume import score_relative_volume

    raw = score_relative_volume(df)
    if raw >= 8.0:
        return max_pts, "rel_vol_2x"
    if raw >= 5.0:
        return max_pts * 0.7, "rel_vol_1.5x"
    if raw >= 3.0:
        return max_pts * 0.4, "rel_vol_1.2x"
    return 0.0, "low_volume"


def sector_rotation_points(
    rs_percentile: float | None,
    *,
    side: str,
    max_pts: float,
) -> tuple[float, str]:
    if rs_percentile is None:
        return 0.0, "missing_rs"
    if side == "long":
        if rs_percentile >= 0.85:
            return max_pts, "rs_top_quintile"
        if rs_percentile >= 0.65:
            return max_pts * 0.75, "rs_upper_tertile"
        if rs_percentile >= 0.45:
            return max_pts * 0.5, "rs_mid"
        return max_pts * 0.25, "rs_weak"
    if rs_percentile <= 0.15:
        return max_pts, "rs_bottom_quintile"
    if rs_percentile <= 0.35:
        return max_pts * 0.75, "rs_lower_tertile"
    if rs_percentile <= 0.55:
        return max_pts * 0.5, "rs_mid"
    return max_pts * 0.25, "rs_strong"


def volatility_regime_points(
    width_pct: float | None,
    max_pts: float,
) -> tuple[float, str]:
    if width_pct is None:
        return 0.0, "missing_width"
    if width_pct >= 0.60:
        return max_pts, "elevated_vol"
    if width_pct >= 0.40:
        return max_pts * (4 / 7), "moderate_vol"
    return 0.0, "compressed_vol"
