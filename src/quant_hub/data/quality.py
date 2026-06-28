"""Data-quality helpers for price and fundamental series."""

from __future__ import annotations

import pandas as pd

from quant_hub.config import MAX_REASONABLE_GROWTH, PRICE_SPIKE_RATIO

__all__ = [
    "has_price_spike",
    "price_spike_ratio",
    "sanitize_growth_rate",
]


def sanitize_growth_rate(growth: float | None) -> float | None:
    """Drop YoY/CAGR values that are unreliable (bad base period or extreme spikes)."""
    if growth is None or pd.isna(growth):
        return None
    value = float(growth)
    if value > MAX_REASONABLE_GROWTH:
        return None
    return value


def price_spike_ratio(df: pd.DataFrame) -> float | None:
    """Latest close divided by the prior 20-session median close."""
    close = df["Close"]
    if len(close) < 21:
        return None
    last = float(close.iloc[-1])
    median = float(close.tail(20).median())
    if median <= 0:
        return None
    return last / median


def has_price_spike(df: pd.DataFrame, *, max_ratio: float = PRICE_SPIKE_RATIO) -> bool:
    """True when the latest close deviates sharply from recent history (split/adjustment errors)."""
    ratio = price_spike_ratio(df)
    if ratio is None:
        return False
    return ratio > max_ratio or ratio < (1 / max_ratio)
