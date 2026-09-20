"""Compute every indicator the rules need once per ticker (NFR review 1.1)."""

from __future__ import annotations

import math

import pandas as pd

from quant_hub.indicators import atr, ema, return_over_days, sma
from quant_hub.sector_swing.adx import adx
from quant_hub.sector_swing.config import SwingParams
from quant_hub.sector_swing.models import SwingIndicators


def _as_float(value: float | None) -> float | None:
    return None if value is None else float(value)


def _last_finite(series: pd.Series, name: str) -> float:
    value = float(series.iloc[-1])
    if not math.isfinite(value):
        raise ValueError(f"{name} is not finite on the last bar")
    return value


def compute_indicators(df: pd.DataFrame, params: SwingParams) -> SwingIndicators:
    """``df`` is a sorted daily OHLCV frame (``ticker_df`` output) of completed bars."""
    n = params.pullback_lookback
    if len(df) < max(params.sma_trend, n + 1, params.adx_window * 2):
        raise ValueError(f"Not enough bars to compute indicators ({len(df)})")

    close = df["Close"].astype(float)
    ema20 = ema(close, params.ema_mid)
    lows_recent = tuple(float(x) for x in df["Low"].astype(float).tail(n))
    ema20_recent = tuple(float(x) for x in ema20.tail(n))
    if not all(math.isfinite(x) for x in (*lows_recent, *ema20_recent)):
        raise ValueError("Non-finite Low/EMA20 inside the pullback window")

    dollar_volume = (close * df["Volume"].astype(float)).tail(params.liquidity_window).mean()

    return SwingIndicators(
        bar_date=pd.Timestamp(df["Date"].iloc[-1]).date(),
        close=float(close.iloc[-1]),
        prev_high=float(df["High"].astype(float).iloc[-2]),
        ema10=_last_finite(ema(close, params.ema_fast), "EMA10"),
        ema20=float(ema20_recent[-1]),
        sma50=_last_finite(sma(close, params.sma_trend), "SMA50"),
        atr14=_last_finite(atr(df.astype({"High": float, "Low": float, "Close": float}),
                               params.atr_window), "ATR"),
        adx14=_last_finite(adx(df, params.adx_window), "ADX"),
        lows_recent=lows_recent,
        ema20_recent=ema20_recent,
        avg_dollar_volume=float(dollar_volume),
        ret_short=_as_float(return_over_days(close, params.rs_short_days)),
        ret_long=_as_float(return_over_days(close, params.rs_long_days)),
    )
