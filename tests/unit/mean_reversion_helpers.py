"""Synthetic daily OHLCV for mean reversion unit tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def synthetic_daily_bars(
    n: int = 600,
    *,
    end_close: float = 100.0,
    trend: float = 0.0002,
    noise: float = 0.005,
    seed: int = 0,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=n)
    close = np.empty(n)
    close[0] = end_close * 0.85
    for i in range(1, n):
        close[i] = close[i - 1] * (1 + trend + rng.normal(0, noise))
    close[-1] = end_close
    high = close * (1 + rng.uniform(0.001, 0.01, n))
    low = close * (1 - rng.uniform(0.001, 0.01, n))
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": rng.integers(800_000, 2_000_000, n),
        }
    )


def synthetic_long_setup_df(n: int = 600) -> pd.DataFrame:
    """Uptrend with last bar at lower band and RSI hook."""
    df = synthetic_daily_bars(n, end_close=150.0, trend=0.0003, seed=42)
    from quant_hub.strategies.mean_reversion.scanner import add_indicators

    enriched = add_indicators(df)
    latest = enriched.iloc[-1]
    target_close = float(latest["BB_Lower"]) * 0.998
    df.iloc[-1, df.columns.get_loc("Close")] = target_close
    df.iloc[-1, df.columns.get_loc("Low")] = target_close * 0.995
    df.iloc[-1, df.columns.get_loc("High")] = target_close * 1.008
    df.iloc[-1, df.columns.get_loc("Volume")] = df["Volume"].iloc[-20:].mean() * 2.2
    return df


def synthetic_short_setup_df(n: int = 600) -> pd.DataFrame:
    """Downtrend with last bar at upper band and RSI hook down."""
    df = synthetic_daily_bars(n, end_close=80.0, trend=-0.0003, seed=7)
    from quant_hub.strategies.mean_reversion.scanner import add_indicators

    enriched = add_indicators(df)
    latest = enriched.iloc[-1]
    target_close = float(latest["BB_Upper"]) * 1.002
    df.iloc[-1, df.columns.get_loc("Close")] = target_close
    df.iloc[-1, df.columns.get_loc("High")] = target_close * 1.008
    df.iloc[-1, df.columns.get_loc("Low")] = target_close * 0.995
    df.iloc[-1, df.columns.get_loc("Volume")] = df["Volume"].iloc[-20:].mean() * 2.0
    return df
