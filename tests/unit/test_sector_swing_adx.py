"""Wilder ADX against a reference implementation and analytic cases."""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from quant_hub import indicators as repo_indicators
from quant_hub.sector_swing.adx import adx


def _reference_adx(high, low, close, window):
    """Straight-line loop of the textbook recursion (alpha = 1/window).

    DI/DX are undefined until ``window`` bars have accumulated; ADX is then seeded at the first
    DX and needs another ``window`` DX observations before it is reported (pandas ``min_periods``).
    """
    n = len(close)
    alpha = 1.0 / window
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = [high[0] - low[0]] + [0.0] * (n - 1)
    for i in range(1, n):
        up, down = high[i] - high[i - 1], low[i - 1] - low[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))

    def smooth(values):
        out, prev = [], None
        for v in values:
            prev = v if prev is None else alpha * v + (1 - alpha) * prev
            out.append(prev)
        return out

    s_tr, s_p, s_m = smooth(tr), smooth(plus_dm), smooth(minus_dm)
    dx = [np.nan] * n
    for i in range(window - 1, n):
        pdi, mdi = 100 * s_p[i] / s_tr[i], 100 * s_m[i] / s_tr[i]
        dx[i] = 100 * abs(pdi - mdi) / (pdi + mdi)

    out = [np.nan] * n
    prev, seen = None, 0
    for i in range(n):
        if np.isnan(dx[i]):
            continue
        prev = dx[i] if prev is None else alpha * dx[i] + (1 - alpha) * prev
        seen += 1
        if seen >= window:
            out[i] = prev
    return out


def test_adx_matches_reference_recursion():
    rng = np.random.default_rng(7)
    close = 100 + np.cumsum(rng.normal(0.1, 1.0, 80))
    high = close + rng.uniform(0.2, 1.0, 80)
    low = close - rng.uniform(0.2, 1.0, 80)
    df = pd.DataFrame({"High": high, "Low": low, "Close": close})

    got = adx(df, 14)
    want = _reference_adx(list(high), list(low), list(close), 14)

    # First value appears once 14 DX observations exist (bar 13 for DX + 13 more).
    assert got.iloc[:26].isna().all()
    assert not np.isnan(got.iloc[26])
    np.testing.assert_allclose(got.iloc[26:].to_numpy(), want[26:], rtol=1e-9)


def test_adx_pure_uptrend_is_100():
    # High/Low step +1 per bar: +DM = 1, -DM = 0, so DX is 100 on every bar.
    i = np.arange(60, dtype=float)
    df = pd.DataFrame({"High": i + 1, "Low": i, "Close": i + 0.5})
    assert adx(df, 14).iloc[-1] == pytest.approx(100.0)


def test_adx_range_bound_is_low():
    i = np.arange(120)
    close = 100 + np.where(i % 2 == 0, 1.0, -1.0)
    df = pd.DataFrame({"High": close + 0.5, "Low": close - 0.5, "Close": close})
    assert adx(df, 14).iloc[-1] < 20


def test_adx_hand_computed_small_window():
    # window=2 (alpha 0.5), 4 bars:
    #   bar        0     1     2     3
    #   +DM        0     1     1     0
    #   -DM        0     0     0     0.5
    #   TR         1     1.5   1.5   1.0
    #   smoothed TR   1   1.25  1.375  1.1875      (seed at bar 0, then 0.5*x + 0.5*prev)
    #   smoothed +DM  0   0.5   0.75   0.375
    #   smoothed -DM  0   0     0      0.25
    #   DX (from bar 1)  100  100  100*|0.375-0.25|/(0.375+0.25) = 20
    #   ADX seeds at the first DX: bar1 = 100, bar2 = 100, bar3 = 0.5*20 + 0.5*100 = 60
    high = [10.0, 11.0, 12.0, 11.5]
    low = [9.0, 10.0, 11.0, 10.5]
    close = [9.5, 10.5, 11.5, 11.0]
    got = adx(pd.DataFrame({"High": high, "Low": low, "Close": close}), 2)
    assert got.iloc[0] != got.iloc[0]  # NaN: fewer than 2 observations
    assert got.iloc[2] == pytest.approx(100.0)
    assert got.iloc[3] == pytest.approx(60.0)
    assert got.iloc[3] == pytest.approx(_reference_adx(high, low, close, 2)[3])


def test_repo_indicators_module_has_no_adx():
    # The spec forbids editing indicators.py; ADX must live in sector_swing.
    assert not hasattr(repo_indicators, "adx")
    assert "adx" not in inspect.getsource(repo_indicators).lower()
