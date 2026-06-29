"""Weekly swing metrics — pullback zone, RS vs SPY, volume ratio."""

from __future__ import annotations

import pandas as pd

from quant_hub.scoring.relative_strength import _rs_ratio
from quant_hub.strategies.swing.constants import (
    PULLBACK_ATR_ABOVE,
    PULLBACK_ATR_BELOW,
    RS_WEEK_LOOKBACKS,
    VOLUME_LOOKBACK_WEEKS,
)


def _min_atr(atr: float, ema20: float) -> float:
    return max(atr, ema20 * 0.005)


def pullback_zone(
    side: str,
    close: float,
    ema20: float,
    atr: float,
) -> tuple[float, float, bool]:
    """Return (lo, hi, in_zone) for ATR-based pullback band around EMA20."""
    atr = _min_atr(atr, ema20)
    if side == "long":
        lo = ema20 - PULLBACK_ATR_BELOW * atr
        hi = ema20 + PULLBACK_ATR_ABOVE * atr
    else:
        lo = ema20 - PULLBACK_ATR_ABOVE * atr
        hi = ema20 + PULLBACK_ATR_BELOW * atr
    return lo, hi, lo <= close <= hi


def pullback_zone_label(side: str) -> str:
    if side == "long":
        return (
            f"Close within EMA20 −{PULLBACK_ATR_BELOW}×ATR "
            f"to EMA20 +{PULLBACK_ATR_ABOVE}×ATR"
        )
    return (
        f"Close within EMA20 −{PULLBACK_ATR_ABOVE}×ATR "
        f"to EMA20 +{PULLBACK_ATR_BELOW}×ATR"
    )


def weekly_volume_ratio(df: pd.DataFrame, *, lookback: int = VOLUME_LOOKBACK_WEEKS) -> float | None:
    if df is None or df.empty or "Volume" not in df.columns or len(df) < lookback + 1:
        return None
    tail = df.tail(lookback + 1)
    current = float(tail["Volume"].iloc[-1])
    prior = tail["Volume"].iloc[:-1]
    avg = float(prior.mean())
    if avg <= 0:
        return None
    return current / avg


def weekly_rs_vs_spy(
    stock_df: pd.DataFrame,
    spy_df: pd.DataFrame,
    *,
    lookbacks: tuple[int, ...] = RS_WEEK_LOOKBACKS,
) -> float | None:
    if stock_df is None or spy_df is None or stock_df.empty or spy_df.empty:
        return None
    stock_close = stock_df["Close"]
    spy_close = spy_df["Close"]
    ratios: list[float] = []
    for weeks in lookbacks:
        ratio = _rs_ratio(stock_close, spy_close, weeks)
        if ratio is not None:
            ratios.append(ratio)
    if not ratios:
        return None
    return sum(ratios) / len(ratios)
