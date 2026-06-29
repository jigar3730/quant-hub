"""Unit tests for swing metrics (ATR pullback, RS, volume)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_hub.strategies.swing.metrics import (
    pullback_zone,
    weekly_rs_vs_spy,
    weekly_volume_ratio,
)


def test_pullback_zone_long_wider_than_fixed_two_percent():
    ema20, atr, close = 100.0, 3.0, 102.5
    lo, hi, in_zone = pullback_zone("long", close, ema20, atr)
    assert lo == 99.25
    assert hi == 103.0
    assert in_zone is True
    # Old fixed 2% band ended at 102.0 — 102.5 would fail that but passes ATR band


def test_weekly_volume_ratio_dry_pullback():
    vols = [1_000_000] * 10 + [600_000]
    df = pd.DataFrame({"Volume": vols})
    ratio = weekly_volume_ratio(df, lookback=10)
    assert ratio is not None
    assert ratio < 0.75


def test_weekly_rs_vs_spy_outperformer():
    n = 80
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="W-FRI")
    spy = pd.DataFrame({"Date": dates, "Close": np.linspace(100, 110, n)})
    stock = pd.DataFrame({"Date": dates, "Close": np.linspace(100, 140, n)})
    ratio = weekly_rs_vs_spy(stock, spy)
    assert ratio is not None
    assert ratio > 1.0
