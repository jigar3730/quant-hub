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
    score_macd_zero_line,
    score_macd_zero_line_from_series,
    score_squeeze_intensity,
    score_tightness_percentile,
    score_volume_vacuum_depth,
    score_trend_proximity_match,
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


def test_eligibility_fails_when_price_not_near_structure():
    close = np.concatenate([np.linspace(40, 70, 255), np.linspace(70, 72, 5)])
    detail = launchpad_eligibility_detail(_df_from_close(close, volume=1_000_000))
    assert detail["passed"] is False
    assert detail["fail_reason"] == "structural_proximity"


def test_eligibility_fails_low_liquidity():
    close = np.concatenate([np.linspace(40, 70, 255), np.linspace(70, 72, 5)])
    detail = launchpad_eligibility_detail(_df_from_close(close, volume=100_000))
    assert detail["passed"] is False
    assert detail["fail_reason"] == "low_liquidity"


def test_squeeze_intensity_rewards_compression():
    close = np.linspace(100, 110, 60)
    high = close + 1.5
    low = close - 1.5
    df = _df_from_ohlcv(close=close, high=high, low=low, volume=np.full(60, 1_000_000))
    score, raw = score_squeeze_intensity(df)
    assert score == 40.0
    assert raw["squeeze_ratio"] < 0.90


def test_volume_vacuum_depth_rewards_dry_up():
    close = np.linspace(100, 110, 60)
    high = close + 1.5
    low = close - 1.5
    volume = np.concatenate([np.full(57, 1_000_000), np.full(3, 300_000)])
    df = _df_from_ohlcv(close=close, high=high, low=low, volume=volume)
    score, raw = score_volume_vacuum_depth(df)
    assert score == 30.0
    assert raw["rvol"] <= 0.45


def test_tightness_percentile_rewards_contracting_bars():
    close = np.full(60, 100.0)
    high = close + np.array([1.5] * 60)
    low = close - np.array([1.0] * 60)
    df = _df_from_ohlcv(close=close, high=high, low=low, volume=np.full(60, 1_000_000))
    score, raw = score_tightness_percentile(df)
    assert score == 15.0
    assert raw["tightness_rank_pct"] <= 0.10


def test_trend_proximity_match_rewards_structure():
    close = np.linspace(100, 120, 260)
    high = close + 0.5
    low = close - 0.5
    spy_close = np.linspace(95, 112, 260)
    spy_high = spy_close + 0.4
    spy_low = spy_close - 0.4
    price_df = _df_from_ohlcv(close=close, high=high, low=low, volume=np.full(260, 1_000_000))
    spy_df = _df_from_ohlcv(close=spy_close, high=spy_high, low=spy_low, volume=np.full(260, 1_000_000))
    score, raw = score_trend_proximity_match(price_df, spy_df)
    assert score == 15.0
    assert raw["relative_strength_positive"] is True
    assert raw["near_support"] is True


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
