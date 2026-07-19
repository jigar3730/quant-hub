"""Launchpad rubric unit tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_hub.config import (
    LAUNCHPAD_NEAR_SUPPORT_FULL_POINTS,
    LAUNCHPAD_NEAR_SUPPORT_PARTIAL_POINTS,
    LAUNCHPAD_RAW_SCORE_MAX,
    LAUNCHPAD_RS_SCORE_POINTS,
    LAUNCHPAD_TIER2_NORMALIZED_MIN,
)
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
    # Rally then consolidate so price sits within the proximity band of EMA50.
    close = np.concatenate([np.linspace(40, 70, 220), np.full(40, 70.0)])
    return _df_from_close(close)


def test_eligibility_passes_constructive_base():
    detail = launchpad_eligibility_detail(_eligible_uptrend_df())
    assert detail["passed"] is True


def test_eligibility_passes_within_five_percent_of_ema50():
    # Mild extension (~3–4%) should pass the widened 5% / ATR gate.
    close = np.concatenate([np.linspace(40, 70, 240), np.linspace(70, 72.5, 20)])
    detail = launchpad_eligibility_detail(_df_from_close(close))
    assert detail["passed"] is True


def test_eligibility_fails_when_price_far_from_structure():
    # Sharp parabolic extension well beyond 5% and ATR band.
    close = np.concatenate([np.linspace(40, 70, 240), np.linspace(70, 95, 20)])
    detail = launchpad_eligibility_detail(_df_from_close(close, volume=1_000_000))
    assert detail["passed"] is False
    assert detail["fail_reason"] == "structural_proximity"


def test_eligibility_fails_low_liquidity():
    close = np.concatenate([np.linspace(40, 70, 220), np.full(40, 70.0)])
    detail = launchpad_eligibility_detail(_df_from_close(close, volume=100_000))
    assert detail["passed"] is False
    assert detail["fail_reason"] == "volume_below_min"


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
    range_half = np.concatenate([np.full(57, 3.0), np.full(3, 0.05)])
    high = close + range_half
    low = close - range_half
    df = _df_from_ohlcv(close=close, high=high, low=low, volume=np.full(60, 1_000_000))
    score, raw = score_tightness_percentile(df)
    assert score == 15.0
    assert raw["tightness_rank_pct"] <= 0.10


def test_trend_proximity_match_rewards_structure():
    # Strong stock rally + consolidation near EMA50; weaker SPY consolidation.
    close = np.concatenate([np.linspace(80, 110, 220), np.full(40, 110.0)])
    high = close + 0.5
    low = close - 0.5
    spy_close = np.concatenate([np.linspace(95, 105, 220), np.full(40, 105.0)])
    spy_high = spy_close + 0.4
    spy_low = spy_close - 0.4
    price_df = _df_from_ohlcv(close=close, high=high, low=low, volume=np.full(260, 1_000_000))
    spy_df = _df_from_ohlcv(close=spy_close, high=spy_high, low=spy_low, volume=np.full(260, 1_000_000))
    score, raw = score_trend_proximity_match(price_df, spy_df)
    assert score == LAUNCHPAD_RS_SCORE_POINTS + LAUNCHPAD_NEAR_SUPPORT_FULL_POINTS
    assert raw["relative_strength_positive"] is True
    assert raw["near_support"] is True
    assert raw["rs_score"] == LAUNCHPAD_RS_SCORE_POINTS
    assert raw["near_support_score"] == LAUNCHPAD_NEAR_SUPPORT_FULL_POINTS


def test_trend_proximity_partial_credit_rs_only():
    # RS+ but price extended beyond near-support bands → RS points only.
    close = np.concatenate([np.linspace(50, 100, 220), np.linspace(100, 118, 40)])
    high = close + 0.5
    low = close - 0.5
    spy_close = np.concatenate([np.linspace(95, 100, 220), np.full(40, 100.0)])
    price_df = _df_from_ohlcv(close=close, high=high, low=low, volume=np.full(260, 1_000_000))
    spy_df = _df_from_ohlcv(
        close=spy_close,
        high=spy_close + 0.4,
        low=spy_close - 0.4,
        volume=np.full(260, 1_000_000),
    )
    score, raw = score_trend_proximity_match(price_df, spy_df)
    assert raw["relative_strength_positive"] is True
    assert raw["rs_score"] == LAUNCHPAD_RS_SCORE_POINTS
    assert score == LAUNCHPAD_RS_SCORE_POINTS
    assert raw["near_support_score"] == 0.0


def test_trend_proximity_partial_credit_near_support_only():
    # Near EMA50 but lagging SPY on the ratio → near-support points only.
    close = np.concatenate([np.linspace(90, 100, 220), np.full(40, 100.0)])
    spy_close = np.concatenate([np.linspace(80, 120, 220), np.full(40, 120.0)])
    price_df = _df_from_ohlcv(
        close=close, high=close + 0.5, low=close - 0.5, volume=np.full(260, 1_000_000)
    )
    spy_df = _df_from_ohlcv(
        close=spy_close,
        high=spy_close + 0.4,
        low=spy_close - 0.4,
        volume=np.full(260, 1_000_000),
    )
    score, raw = score_trend_proximity_match(price_df, spy_df)
    assert raw["relative_strength_positive"] is False
    assert raw["rs_score"] == 0.0
    assert raw["near_support"] is True
    assert score == raw["near_support_score"]
    assert score in (
        LAUNCHPAD_NEAR_SUPPORT_FULL_POINTS,
        LAUNCHPAD_NEAR_SUPPORT_PARTIAL_POINTS,
    )


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
        "macd_zero_line": FactorResult("macd_zero_line", 25.0, 25.0),  # gate only
        "squeeze_intensity": FactorResult("squeeze_intensity", 40.0, 40.0),
        "tightness_percentile": FactorResult("tightness_percentile", 15.0, 15.0),
        "volume_vacuum_depth": FactorResult("volume_vacuum_depth", 30.0, 30.0),
        "trend_proximity_match": FactorResult("trend_proximity_match", 15.0, 15.0),
    }
    aggregate_launchpad_ticker(ticker, MarketRegime("neutral", 1.0))
    assert ticker.raw_score == LAUNCHPAD_RAW_SCORE_MAX
    assert ticker.normalized_score == 100.0


def test_macd_gate_does_not_inflate_raw_score():
    ticker = TickerResult(ticker="TEST", eligible=True, filter_reason="eligible")
    ticker.factors = {
        "macd_zero_line": FactorResult("macd_zero_line", 25.0, 25.0),
        "squeeze_intensity": FactorResult("squeeze_intensity", 40.0, 40.0),
    }
    aggregate_launchpad_ticker(ticker, MarketRegime("neutral", 1.0))
    assert ticker.raw_score == 40.0


def test_trend_proximity_rejects_absolute_dollar_rs():
    """Stock below SPY in dollars can still have positive relative strength near support."""
    close = np.concatenate([np.linspace(40, 70, 220), np.full(40, 70.0)])
    high = close + 0.5
    low = close - 0.5
    spy_close = np.concatenate([np.linspace(480, 500, 220), np.full(40, 500.0)])
    spy_high = spy_close + 0.4
    spy_low = spy_close - 0.4
    price_df = _df_from_ohlcv(close=close, high=high, low=low, volume=np.full(260, 1_000_000))
    spy_df = _df_from_ohlcv(
        close=spy_close, high=spy_high, low=spy_low, volume=np.full(260, 1_000_000)
    )
    score, raw = score_trend_proximity_match(price_df, spy_df)
    assert raw["relative_strength_positive"] is True
    assert raw["price_ema50"] < raw["spy_ema50"]
    assert raw["near_support"] is True
    assert score == LAUNCHPAD_RS_SCORE_POINTS + LAUNCHPAD_NEAR_SUPPORT_FULL_POINTS


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
