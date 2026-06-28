"""Tests for ETF vs stock breakout eligibility."""

from __future__ import annotations

import pandas as pd

from quant_hub.filters.eligibility import eligibility_detail


def _sample_df(*, rows: int = 260, price: float = 50.0, volume: float = 1_000_000) -> pd.DataFrame:
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


def test_etf_mode_passes_without_stage2_trend_stack():
    # Flat MA stack would fail stock mode (price == all SMAs)
    df = _sample_df()
    stock = eligibility_detail(df, mode="stock")
    etf = eligibility_detail(df, mode="etf")
    assert stock["passed"] is False
    assert stock["fail_reason"] == "trend_misaligned"
    assert etf["passed"] is True


def test_etf_mode_uses_lower_liquidity_threshold():
    df = _sample_df(volume=600_000)
    assert eligibility_detail(df, mode="stock")["fail_reason"] == "low_liquidity"
    assert eligibility_detail(df, mode="etf")["passed"] is True
