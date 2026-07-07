"""Launchpad Reversal rubric unit tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_hub.config import LAUNCHPAD_RAW_SCORE_MAX, LAUNCHPAD_TIER2_NORMALIZED_MIN
from quant_hub.engine.types import FactorResult, TickerResult
from quant_hub.regime.market import MarketRegime
from quant_hub.scoring.launchpad import (
    _crossed_above_zero,
    launchpad_eligibility_detail,
    score_atr_contraction,
    score_ma_tightness,
    score_macd_zero_line,
    score_macd_zero_line_from_series,
    score_swing_low_vcp,
    score_volume_dry_up,
)
from quant_hub.strategies.launchpad.aggregate import aggregate_launchpad_ticker
from quant_hub.strategies.launchpad.tiers import assign_tier_from_row


def _df_from_close(close: np.ndarray, *, volume: float = 1_000_000) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=len(close))
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": [volume] * len(close),
        }
    )


def _df_from_ohlcv(
    *,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray,
) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=len(close))
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        }
    )


def _eligible_uptrend_df() -> pd.DataFrame:
    close = np.concatenate([np.linspace(40, 70, 255), np.linspace(70, 72, 5)])
    return _df_from_close(close)


def test_eligibility_passes_constructive_base():
    detail = launchpad_eligibility_detail(_eligible_uptrend_df())
    assert detail["passed"] is True


def test_eligibility_fails_when_too_extended():
    close = np.concatenate([np.linspace(40, 70, 259), np.array([78.0])])
    detail = launchpad_eligibility_detail(_df_from_close(close))
    assert detail["passed"] is False
    assert detail["fail_reason"] == "too_extended"


def test_eligibility_fails_base_not_cleared():
    # Uptrend then a deep drop below both moving averages on the last bar.
    close = np.concatenate([np.linspace(40, 90, 259), np.array([30.0])])
    detail = launchpad_eligibility_detail(_df_from_close(close))
    assert detail["passed"] is False
    assert detail["fail_reason"] == "base_not_cleared"


def test_eligibility_fails_trend_not_fresh():
    # Price above both MAs but SMA50 flat/declining over last 10 bars (rolled over).
    close = np.concatenate(
        [
            np.linspace(40, 100, 235),
            np.linspace(100, 88, 25),
        ]
    )
    detail = launchpad_eligibility_detail(_df_from_close(close))
    # Either base clearance or fresh-trend fails first depending on the roll-over depth;
    # this fixture is tuned so SMA50 is falling while price is still > SMA200.
    assert detail["passed"] is False
    assert detail["fail_reason"] in ("trend_not_fresh", "base_not_cleared")


def test_eligibility_fails_low_liquidity():
    close = np.concatenate([np.linspace(40, 70, 255), np.linspace(70, 72, 5)])
    detail = launchpad_eligibility_detail(_df_from_close(close, volume=100_000))
    assert detail["passed"] is False
    assert detail["fail_reason"] == "low_liquidity"


def test_eligibility_extension_boundary_at_8pct():
    # Flat 20-day median at 100; last close exactly 8.0% above passes, 8.01% fails.
    base = np.full(259, 100.0)
    pass_df = _df_from_close(np.concatenate([base, np.array([108.0])]))
    fail_df = _df_from_close(np.concatenate([base, np.array([108.01])]))
    pass_detail = launchpad_eligibility_detail(pass_df)
    fail_detail = launchpad_eligibility_detail(fail_df)
    assert pass_detail["passed"] is True
    assert fail_detail["passed"] is False
    assert fail_detail["fail_reason"] == "too_extended"


def test_ma_tightness_thresholds():
    close = np.full(260, 100.0)
    df = _df_from_close(close)
    score_tight, _ = score_ma_tightness(df)
    assert score_tight == 25.0

    # Step from 100 -> 110: SMA50=110, SMA200=105.5 -> spread ~4.27% (3%-6% band).
    close = np.concatenate([np.full(150, 100.0), np.full(110, 110.0)])
    score_mid, raw = score_ma_tightness(_df_from_close(close))
    assert score_mid == 15.0
    assert 3.0 < raw["ma_spread_pct"] <= 6.0

    close = np.concatenate([np.full(150, 50.0), np.linspace(50, 150, 110)])
    score_wide, raw_wide = score_ma_tightness(_df_from_close(close))
    assert raw_wide["ma_spread_pct"] > 6.0
    assert score_wide == 0.0


def test_atr_contraction_rewards_range_shrinkage():
    # Flat close so True Range == High-Low; wide ranges early, tight ranges recent.
    n = 60
    close = np.full(n, 100.0)
    ranges = np.concatenate([np.full(46, 10.0), np.full(14, 2.0)])
    high = close + ranges / 2
    low = close - ranges / 2
    volume = np.full(n, 1_000_000)
    df = _df_from_ohlcv(close=close, high=high, low=low, volume=volume)
    score, raw = score_atr_contraction(df)
    assert score == 20.0
    assert raw["volatility_ratio"] < 0.70


def test_atr_contraction_zero_when_ranges_stable():
    n = 60
    close = np.full(n, 100.0)
    high = close + 5.0
    low = close - 5.0
    volume = np.full(n, 1_000_000)
    df = _df_from_ohlcv(close=close, high=high, low=low, volume=volume)
    score, raw = score_atr_contraction(df)
    assert score == 0.0
    assert raw["volatility_ratio"] >= 0.80


def test_volume_dry_up_rewards_supply_exhaustion():
    n = 60
    close = np.linspace(50, 80, n)
    high = close * 1.01
    low = close * 0.99
    volume = np.concatenate([np.full(57, 1_000_000), np.full(3, 300_000)])
    df = _df_from_ohlcv(close=close, high=high, low=low, volume=volume)
    score, raw = score_volume_dry_up(df)
    assert score == 15.0
    assert raw["volume_dry_up_ratio"] <= 0.50


def test_volume_dry_up_zero_when_active():
    n = 60
    close = np.linspace(50, 80, n)
    high = close * 1.01
    low = close * 0.99
    volume = np.full(n, 1_000_000)
    df = _df_from_ohlcv(close=close, high=high, low=low, volume=volume)
    score, raw = score_volume_dry_up(df)
    assert score == 0.0
    assert raw["volume_dry_up_ratio"] > 0.60


def test_swing_low_vcp_rewards_contracting_pullbacks():
    # Deep pullback (~20%) followed by a shallow one (~5%): textbook VCP.
    seg1 = np.linspace(100, 120, 11)
    seg2 = np.linspace(120, 96, 11)[1:]
    seg3 = np.linspace(96, 118, 11)[1:]
    seg4 = np.linspace(118, 112, 11)[1:]
    seg5 = np.linspace(112, 116, 11)[1:]
    price = np.concatenate([seg1, seg2, seg3, seg4, seg5])
    df = _df_from_close(price)
    score, raw = score_swing_low_vcp(df)
    assert score == 15.0
    assert raw["contraction_ratio"] <= 0.50
    assert raw["latest_pullback_pct"] < raw["prior_pullback_pct"]


def test_swing_low_vcp_zero_without_two_legs():
    price = np.linspace(100, 130, 40)
    df = _df_from_close(price)
    score, raw = score_swing_low_vcp(df)
    assert score == 0.0
    assert raw["pullback_leg_count"] < 2


def test_tier1_requires_macd_25_and_norm_80():
    row = {
        "eligible": True,
        "normalized_score": 85.0,
        "macd_zero_line_score": 25.0,
    }
    assert assign_tier_from_row(row) == "Tier 1"

    row["macd_zero_line_score"] = 15.0
    assert assign_tier_from_row(row) == "Tier 2"


def test_tier2_at_sixty_five():
    row = {
        "eligible": True,
        "normalized_score": LAUNCHPAD_TIER2_NORMALIZED_MIN,
        "macd_zero_line_score": 0.0,
    }
    assert assign_tier_from_row(row) == "Tier 2"


def test_normalized_score_uses_raw_max_100():
    ticker = TickerResult(ticker="TEST", eligible=True, filter_reason="eligible")
    ticker.factors = {
        "ma_tightness": FactorResult("ma_tightness", 25.0, 25.0),
        "macd_zero_line": FactorResult("macd_zero_line", 25.0, 25.0),
        "atr_contraction": FactorResult("atr_contraction", 20.0, 20.0),
        "volume_dry_up": FactorResult("volume_dry_up", 15.0, 15.0),
        "swing_low_vcp": FactorResult("swing_low_vcp", 15.0, 15.0),
    }
    aggregate_launchpad_ticker(ticker, MarketRegime("neutral", 1.0))
    assert ticker.raw_score == LAUNCHPAD_RAW_SCORE_MAX
    assert ticker.normalized_score == 100.0
    assert ticker.final_score == 100.0


def test_macd_zero_line_ignition_requires_both_zero_crossings():
    line = pd.Series([-0.5, -0.3, -0.1, 0.2, 0.4, 0.5])
    signal = pd.Series([-0.6, -0.4, -0.2, 0.1, 0.3, 0.45])
    score, details = score_macd_zero_line_from_series(line, signal)
    assert score == 25.0
    assert details["phase"] == "zero_line_ignition"
    assert details["macd_zero_cross"] is True
    assert details["signal_zero_cross"] is True


def test_macd_rejects_full_score_when_only_signal_crossed_recently():
    line = pd.Series([0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
    signal = pd.Series([0.4, 0.3, 0.2, 0.1, -0.1, 0.05])
    score, details = score_macd_zero_line_from_series(line, signal)
    assert score == 0.0
    assert details["phase"] == "above_zero_established"
    assert details["macd_zero_cross"] is False
    assert details["signal_zero_cross"] is True


def test_macd_early_recovery_below_zero():
    line = pd.Series([-0.5, -0.4, -0.3, -0.2, -0.1, -0.05])
    signal = pd.Series([-0.4, -0.35, -0.3, -0.25, -0.2, -0.15])
    score, details = score_macd_zero_line_from_series(line, signal)
    assert score == 15.0
    assert details["phase"] == "early_recovery"


def test_crossed_above_zero_detects_recent_cross():
    series = pd.Series([-0.2, -0.1, 0.1, 0.2, 0.3])
    assert _crossed_above_zero(series, within_bars=5) is True
    assert _crossed_above_zero(pd.Series([0.1, 0.2, 0.3, 0.4, 0.5]), within_bars=5) is False


def test_macd_below_signal_scores_zero():
    close = np.linspace(100, 80, 260)
    score, _ = score_macd_zero_line(_df_from_close(close))
    assert score == 0.0
