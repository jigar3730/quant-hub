"""Rules R1-R6 and sizing R7 at their exact boundaries (pure inputs, no frames)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from quant_hub.sector_swing import rules
from quant_hub.sector_swing.config import DEFAULT_PARAMS as P
from quant_hub.sector_swing.models import SwingIndicators
from quant_hub.sector_swing.sizing import build_trade_plan, position_size


def ind(**kw) -> SwingIndicators:
    base = dict(
        bar_date=date(2026, 9, 18),
        close=100.0,
        prev_high=99.0,
        ema10=98.0,
        ema20=97.0,
        sma50=95.0,
        atr14=2.0,
        adx14=30.0,
        lows_recent=(97.0, 96.0, 96.5, 97.0, 98.0, 99.0),
        ema20_recent=(97.0, 97.0, 97.0, 97.0, 97.0, 97.0),
        avg_dollar_volume=1e8,
        ret_short=0.10,
        ret_long=0.20,
    )
    base.update(kw)
    return SwingIndicators(**base)


# ---- R1 regime ----
def test_r1_regime_needs_both_smas():
    assert rules.check_regime(101, 100, 90).passed
    assert not rules.check_regime(101, 100, 105).passed  # below SMA200
    assert not rules.check_regime(101, 105, 90).passed  # below SMA50
    assert not rules.check_regime(100, 100, 90).passed  # equal is not "above"


# ---- R2 leadership ----
def test_r2_relative_strength_score_is_mean_excess_in_pct_points():
    # 0.5*(0.10-0.02) + 0.5*(0.20-0.04) = 0.12 -> 12 percentage points
    assert rules.relative_strength_pct(ind(), 0.02, 0.04) == pytest.approx(12.0)
    assert rules.relative_strength_pct(ind(ret_long=None), 0.02, 0.04) is None


@pytest.mark.parametrize(
    "rank, rs, ok",
    [
        (1, 0.01, True),
        (4, 3.0, True),  # rank boundary: TOP_N_LEADERS is inclusive
        (5, 3.0, False),
        (1, 0.0, False),  # RS must be strictly positive
        (1, -2.0, False),
        (None, 5.0, False),
    ],
)
def test_r2_leader_boundaries(rank, rs, ok):
    assert rules.check_leader(rank, rs, P).passed is ok


def test_r2_positive_rs_can_be_disabled():
    assert rules.check_leader(1, -1.0, replace(P, require_positive_rs=False)).passed


# ---- R3 trend ----
@pytest.mark.parametrize(
    "kw, ok",
    [
        ({}, True),
        ({"adx14": 20.0}, True),  # ADX boundary inclusive
        ({"adx14": 19.99}, False),
        ({"close": 95.0}, False),  # Close == SMA50 is not above
        ({"ema20": 95.0}, False),  # EMA20 == SMA50 is not above
        ({"ema20": 94.0}, False),
    ],
)
def test_r3_trend(kw, ok):
    assert rules.check_trend(ind(**kw), P).passed is ok


# ---- R4 pullback (1.005 tolerance) ----
def test_r4_pullback_tolerance_boundary():
    ema = (100.0,) * 6
    touch = ind(lows_recent=(105.0, 104.0, 103.0, 102.0, 101.0, 100.5), ema20_recent=ema)
    assert rules.check_pullback(touch, P).passed  # 100.5 == 100 * 1.005
    miss = ind(lows_recent=(105.0, 104.0, 103.0, 102.0, 101.0, 100.51), ema20_recent=ema)
    assert not rules.check_pullback(miss, P).passed
    assert rules.check_pullback(miss, replace(P, pullback_tolerance=1.006)).passed


def test_r4_any_bar_in_window_counts():
    ema = (100.0,) * 6
    early_touch = ind(lows_recent=(99.0, 103.0, 104.0, 105.0, 106.0, 107.0), ema20_recent=ema)
    assert rules.check_pullback(early_touch, P).passed


# ---- R5 trigger ----
@pytest.mark.parametrize(
    "kw, ok",
    [
        ({}, True),
        ({"close": 99.0}, False),  # Close == prior High
        ({"close": 98.0, "prev_high": 97.0}, False),  # Close == EMA10
        ({"close": 98.5, "prev_high": 97.0}, True),
        ({"close": 101.0, "prev_high": 102.0}, False),
    ],
)
def test_r5_trigger(kw, ok):
    assert rules.check_trigger(ind(**kw), P).passed is ok


# ---- R6 stop ----
def test_r6_stop_level_and_cap_boundary():
    # stop = pullback_low - 0.25*ATR; risk = close - stop
    at_cap = ind(close=100.0, atr14=2.0, lows_recent=(95.5,) * 6)  # risk = 100-(95.5-0.5) = 5.0
    result, stop, risk = rules.check_stop(at_cap, P)
    assert stop == pytest.approx(95.0)
    assert risk == pytest.approx(5.0)  # exactly 2.5 x ATR
    assert result.passed
    over = ind(close=100.0, atr14=2.0, lows_recent=(95.49,) * 6)
    assert not rules.check_stop(over, P)[0].passed


def test_r6_rejects_non_positive_risk():
    weird = ind(close=90.0, atr14=2.0, lows_recent=(95.0,) * 6)  # close below the stop
    assert not rules.check_stop(weird, P)[0].passed


# ---- R7 sizing ----
def test_sizing_risk_limited():
    # 50k * 1% = 500 risk; 5/share -> 100 shares (position 5,000 < 15,000 cap)
    assert position_size(50_000, 0.01, 0.30, entry=50.0, risk_per_share=5.0) == 100


def test_sizing_cap_limited():
    # risk-limited 500 shares, but 30% of 50k = 15,000 / 500 = 30 shares
    assert position_size(50_000, 0.01, 0.30, entry=500.0, risk_per_share=1.0) == 30


def test_sizing_floors_and_zero():
    assert position_size(50_000, 0.01, 0.30, entry=10.0, risk_per_share=125.0) == 4  # 500/125 = 4.0 exactly
    assert position_size(50_000, 0.01, 0.30, entry=10.0, risk_per_share=160.0) == 3  # 3.125 -> 3
    assert position_size(50_000, 0.01, 0.30, entry=100.0, risk_per_share=1000.0) == 0  # 0.5 -> 0


@pytest.mark.parametrize("entry, rps", [(100.0, 0.0), (100.0, -1.0), (0.0, 1.0), (-5.0, 1.0)])
def test_sizing_rejects_entry_at_or_below_stop(entry, rps):
    assert position_size(50_000, 0.01, 0.30, entry=entry, risk_per_share=rps) == 0


def test_trade_plan_levels():
    i = ind(close=100.0, atr14=2.0)
    plan = build_trade_plan(i, P, stop=96.0, risk_per_share=4.0, equity=50_000, risk_pct=0.01)
    assert plan.entry_ref == 100.0
    assert plan.target_2r == pytest.approx(108.0)  # entry + 2R
    assert plan.chase_limit == pytest.approx(101.0)  # entry + 0.5 ATR
    assert plan.invalidation == plan.stop == 96.0
    assert plan.shares == 125  # 500 / 4
    assert plan.risk_dollars == pytest.approx(500.0)
    assert plan.position_dollars == pytest.approx(12_500.0)
    assert plan.stop_atr_multiple == pytest.approx(2.0)
    assert plan.to_dict()["regime_blocked"] is False
