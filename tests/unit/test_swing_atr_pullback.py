"""Tests for ATR pullback gate and RS/volume scoring components."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_hub.strategies.swing.scanner import add_indicators, analyze_swing
from quant_hub.strategies.swing.scoring import score_swing_quality


def _synthetic_uptrend_weeks(n: int = 120, *, last_close_mult: float = 1.005) -> pd.DataFrame:
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="W-FRI")
    close = np.linspace(100, 150, n) + np.random.default_rng(0).normal(0, 0.5, n)
    close[-1] = close[-2] * last_close_mult
    vol = np.full(n, 1_000_000)
    vol[-1] = 650_000
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": vol,
        }
    )


def _synthetic_spy(n: int = 120) -> pd.DataFrame:
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="W-FRI")
    close = np.linspace(100, 120, n)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": np.full(n, 5_000_000),
        }
    )


def test_rule_breakdown_includes_rs_and_volume():
    stock = _synthetic_uptrend_weeks(120, last_close_mult=1.08)
    spy = _synthetic_spy(120)
    analysis = analyze_swing(stock, "TEST", min_bars=60, spy_df=spy, rs_percentile=0.9)
    enriched = add_indicators(stock)
    result = score_swing_quality(analysis, enriched)
    rules = {r["rule"] for r in result.rule_breakdown}
    assert "rs_market" in rules
    assert "volume_pullback" in rules
    assert result.rs_ratio_score > 0
    assert result.volume_score > 0


def test_atr_pullback_allows_moderate_extension_vs_old_two_percent():
    """Price modestly above old 2% EMA band may still pass ATR pullback gate."""
    df = _synthetic_uptrend_weeks(120, last_close_mult=1.0)
    enriched = add_indicators(df)
    latest = enriched.iloc[-1]
    ema20 = float(latest["EMA20"])
    atr = float(latest["ATR"])
    # Set close to EMA20 + 0.5*ATR (inside +1.0 ATR band, may exceed +2%)
    target = ema20 + 0.5 * atr
    df.iloc[-1, df.columns.get_loc("Close")] = target
    df.iloc[-1, df.columns.get_loc("High")] = target + 0.5
    df.iloc[-1, df.columns.get_loc("Low")] = target - 0.5
    analysis = analyze_swing(df, "TEST", min_bars=60, spy_df=_synthetic_spy(120))
    pull = next(c for c in analysis.long_checks if c.rule == "long_pullback_zone")
    assert pull.passed is True
