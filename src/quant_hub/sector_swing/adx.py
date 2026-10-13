"""Wilder ADX (the repo's ``indicators.py`` has none and must stay untouched)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average Directional Index with Wilder smoothing (alpha = 1/window).

    Smoothing is a recursive EMA seeded from the first observation (``adjust=False``), the same
    convention as ``indicators.rsi``. Values are NaN until ``window`` bars have accumulated.
    """
    high, low, close = df["High"], df["Low"], df["Close"]
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index
    )

    prev_close = close.shift(1)
    true_range = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)

    alpha = 1.0 / window
    smoothed_tr = true_range.ewm(alpha=alpha, adjust=False, min_periods=window).mean()
    plus_di = 100 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=window).mean() / smoothed_tr
    minus_di = (
        100 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=window).mean() / smoothed_tr
    )
    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    return dx.ewm(alpha=alpha, adjust=False, min_periods=window).mean()
