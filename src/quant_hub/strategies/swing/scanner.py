"""Weekly swing setup scanner — ported from finance-vibe swing_scanner.py."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_hub.indicators import atr, ema, macd_histogram, rsi


@dataclass(frozen=True)
class SwingSetup:
    ticker: str
    setup_type: str  # SETUP_LONG | SETUP_SHORT
    close: float
    ema20: float
    ema50: float
    rsi: float
    atr: float
    notes: str


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["EMA20"] = ema(out["Close"], 20)
    out["EMA50"] = ema(out["Close"], 50)
    out["MACD_Hist"] = macd_histogram(out["Close"])
    out["RSI"] = rsi(out["Close"], 14)
    out["ATR"] = atr(out, 14)
    return out.dropna()


def momentum_ready_long(df: pd.DataFrame) -> bool:
    h = df["MACD_Hist"].tail(3)
    if len(h) < 3:
        return False
    is_rising = h.iloc[-1] > h.iloc[-2]
    was_rising = h.iloc[-2] > h.iloc[-3]
    hist_std = df["MACD_Hist"].rolling(20).std().iloc[-1]
    not_overextended = h.iloc[-1] < hist_std * 2
    return bool(is_rising and was_rising and not_overextended)


def momentum_ready_short(df: pd.DataFrame) -> bool:
    h = df["MACD_Hist"].tail(3)
    if len(h) < 3:
        return False
    is_falling = h.iloc[-1] < h.iloc[-2]
    was_falling = h.iloc[-2] < h.iloc[-3]
    hist_std = df["MACD_Hist"].rolling(20).std().iloc[-1]
    not_overextended = h.iloc[-1] > -hist_std * 2
    return bool(is_falling and was_falling and not_overextended)


def evaluate_setup(df: pd.DataFrame, *, rsi_min_long: float = 45) -> dict | None:
    """Return setup dict or None. Logic matches finance-vibe weekly profile."""
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    close = float(latest["Close"])
    ema20 = float(latest["EMA20"])
    ema50 = float(latest["EMA50"])
    rsi_val = float(latest["RSI"])

    if (
        ema20 > ema50
        and ema50 > prev["EMA50"]
        and ema20 <= close <= ema20 * 1.02
        and rsi_min_long <= rsi_val <= 60
        and momentum_ready_long(df)
    ):
        return {"Setup Type": "SETUP_LONG", "Notes": "Pullback into 20EMA"}

    if (
        ema20 < ema50
        and ema50 < prev["EMA50"]
        and ema20 * 0.98 <= close <= ema20
        and 50 <= rsi_val <= 65
        and momentum_ready_short(df)
    ):
        return {"Setup Type": "SETUP_SHORT", "Notes": "Pullback into 20EMA"}

    return None


def scan_ticker(df: pd.DataFrame, ticker: str, *, min_bars: int = 60) -> SwingSetup | None:
    if len(df) < min_bars:
        return None
    enriched = add_indicators(df)
    if len(enriched) < 3:
        return None
    setup = evaluate_setup(enriched)
    if not setup:
        return None
    latest = enriched.iloc[-1]
    return SwingSetup(
        ticker=ticker.upper(),
        setup_type=setup["Setup Type"],
        close=round(float(latest["Close"]), 2),
        ema20=round(float(latest["EMA20"]), 2),
        ema50=round(float(latest["EMA50"]), 2),
        rsi=round(float(latest["RSI"]), 2),
        atr=round(float(latest["ATR"]), 2),
        notes=setup["Notes"],
    )
