"""Breakout rubric unit tests (normalization, tiers, compression lag, eligibility)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_hub.config import (
    BREAKOUT_TIER2_NORMALIZED_MIN,
    RAW_SCORE_MAX,
)
from quant_hub.filters.eligibility import eligibility_detail
from quant_hub.scoring.volatility import (
    bollinger_compression_pct_rank,
    score_bollinger_compression,
)
from quant_hub.strategies.breakout.aggregate import aggregate_breakout_ticker
from quant_hub.strategies.breakout.tiers import assign_tier_from_row
from quant_hub.engine.types import FactorResult, TickerResult
from quant_hub.regime.market import MarketRegime


def _flat_df(*, rows: int = 260, price: float = 50.0, volume: float = 1_000_000) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=rows)
    close = pd.Series([price] * rows, dtype=float)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": [volume] * rows,
        }
    )


def _uptrend_df() -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=260)
    close = pd.Series(np.linspace(40, 80, 260), dtype=float)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": [1_000_000] * 260,
        }
    )


def test_normalized_score_uses_earnable_raw_max():
    ticker = TickerResult(ticker="TEST", eligible=True, filter_reason="eligible")
    ticker.factors = {
        "pattern": FactorResult("pattern", 5.0, 5.0),
        "resistance": FactorResult("resistance", 5.0, 5.0),
        "compression": FactorResult("compression", 15.0, 15.0),
        "rs_market": FactorResult("rs_market", 20.0, 20.0),
        "rs_sector": FactorResult("rs_sector", 15.0, 15.0),
        "accumulation": FactorResult("accumulation", 12.0, 12.0),
        "relative_volume": FactorResult("relative_volume", 8.0, 8.0),
    }
    aggregate_breakout_ticker(ticker, MarketRegime("strong", 1.0))
    assert ticker.raw_score == RAW_SCORE_MAX
    assert ticker.normalized_score == 100.0


def test_tier2_threshold_at_sixty():
    row = {
        "eligible": True,
        "normalized_score": BREAKOUT_TIER2_NORMALIZED_MIN,
        "final_adjusted_score": 55.0,
        "compression_score": 0.0,
        "accumulation_score": 0.0,
        "relative_volume_score": 0.0,
    }
    assert assign_tier_from_row(row) == "Tier 2"


def test_relaxed_trend_passes_early_base():
    df = _uptrend_df()
    detail = eligibility_detail(df, mode="stock")
    assert detail["passed"] is True


def test_pullback_below_sma50_still_eligible_when_above_sma200():
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=260)
    close = np.concatenate(
        [
            np.linspace(50, 110, 255),
            np.array([102.0, 100.0, 98.0, 96.0, 94.0]),
        ]
    )
    df = pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": [1_000_000] * len(dates),
        }
    )
    detail = eligibility_detail(df, mode="stock")
    assert detail["passed"] is True
    trend = next(c for c in detail["checks"] if c["rule"] == "trend_alignment")
    assert trend["value"]["price"] < trend["value"]["sma50"]
    assert trend["value"]["price"] > trend["value"]["sma200"]


def test_allows_deeper_pullback_from_52w_high():
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=260)
    lows = np.concatenate([np.full(200, 40.0), np.linspace(40, 50, 60)])
    highs = np.concatenate([np.linspace(80, 100, 200), np.full(60, 100.0)])
    close = np.concatenate([np.linspace(52, 70, 200), np.full(60, 65.0)])
    df = pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": highs,
            "Low": lows,
            "Close": close,
            "Volume": [1_000_000] * len(dates),
        }
    )
    detail = eligibility_detail(df, mode="stock")
    assert detail["passed"] is True


def test_flat_ma_still_fails_trend_gate():
    detail = eligibility_detail(_flat_df(), mode="stock")
    assert detail["passed"] is False
    assert detail["fail_reason"] == "trend_misaligned"


def test_rejects_more_than_40pct_below_52w_high():
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=260)
    highs = np.full(260, 100.0)
    close = np.linspace(40, 58, 260)  # ends ~45% below 100-high
    df = pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": highs,
            "Low": close * 0.98,
            "Close": close,
            "Volume": [1_000_000] * len(dates),
        }
    )
    detail = eligibility_detail(df, mode="stock")
    assert detail["passed"] is False
    assert detail["fail_reason"] == "too_far_from_52w_high"


def test_compression_lag_uses_prior_bar():
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=200)
    rng = np.random.default_rng(0)
    # Tight range then wide last bar (simulated breakout expansion)
    tight = 100 + rng.normal(0, 0.1, 198).cumsum()
    wide = np.append(tight, [tight[-1] + 5.0, tight[-1] + 8.0])
    close = pd.Series(wide, dtype=float)
    df = pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": [1_000_000] * len(dates),
        }
    )
    score_today = score_bollinger_compression(df, lag_days=0)
    score_lag = score_bollinger_compression(df, lag_days=1)
    assert score_lag >= score_today
    assert bollinger_compression_pct_rank(df, lag_days=1)[0] is not None
