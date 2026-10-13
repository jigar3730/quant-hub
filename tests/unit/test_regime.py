"""Unit tests for SPY market regime classification."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from quant_hub.regime.market import regime_detail


def _spy_df(n: int, *, start_price: float = 400.0, daily_return: float = 0.001) -> pd.DataFrame:
    prices = start_price * (1 + daily_return) ** np.arange(n)
    return pd.DataFrame(
        {
            "Close": prices,
            "High": prices * 1.002,
            "Low": prices * 0.998,
        }
    )


def test_regime_detail_strong_uptrend():
    df = _spy_df(260, daily_return=0.002)
    detail = regime_detail(df)
    assert detail["label"] == "strong"
    assert detail["multiplier"] == 1.0


def test_regime_detail_raises_on_insufficient_history():
    df = _spy_df(150)  # fewer than the 200 rows sma(close, 200) needs
    with pytest.raises(RuntimeError, match="Insufficient SPY history"):
        regime_detail(df)
