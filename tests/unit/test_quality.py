import numpy as np
import pandas as pd

from quant_hub.data.quality import (
    drop_incomplete_ohlcv_bars,
    growth_to_percent,
    has_price_spike,
    max_bar_date,
    normalize_debt_to_equity,
    normalize_rate_decimal,
    ohlcv_has_incomplete_last_bar,
    ohlcv_is_stale,
    price_spike_ratio,
    sanitize_growth_rate,
    validate_ohlcv,
)
from quant_hub.lynch.metrics import compute_peg


def test_sanitize_growth_rate_rejects_hypergrowth():
    assert sanitize_growth_rate(4.0) is None
    assert sanitize_growth_rate(0.25) == 0.25


def test_normalize_rate_decimal():
    assert normalize_rate_decimal(0.15) == 0.15
    assert normalize_rate_decimal(15.0) == 0.15
    assert normalize_rate_decimal(None) is None


def test_normalize_debt_to_equity():
    assert normalize_debt_to_equity(35.0) == 0.35
    assert normalize_debt_to_equity(0.25) == 0.25
    assert normalize_debt_to_equity(1.35) == 1.35


def test_growth_to_percent_and_peg():
    assert growth_to_percent(0.20) == 20.0
    assert growth_to_percent(20.0) == 20.0
    assert compute_peg(15, 0.20) == 0.75
    assert compute_peg(15, 20) == 0.75


def test_price_spike_detection():
    n = 30
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="B")
    normal = pd.DataFrame({"Date": dates, "Close": np.full(n, 100.0)})
    assert has_price_spike(normal) is False

    spiked = normal.copy()
    spiked.loc[spiked.index[-1], "Close"] = 400.0
    assert has_price_spike(spiked) is True
    assert price_spike_ratio(spiked) == 4.0


def test_validate_ohlcv_empty():
    result = validate_ohlcv(pd.DataFrame())
    assert result.ok is False
    assert "empty" in result.issues


def test_drop_incomplete_ohlcv_bars_removes_nan_close():
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-08-27", "2026-08-28"]),
            "Open": [100.0, np.nan],
            "High": [101.0, np.nan],
            "Low": [99.0, np.nan],
            "Close": [100.5, np.nan],
            "Volume": [1_000_000, 2_000_000],
        }
    )
    cleaned = drop_incomplete_ohlcv_bars(df)
    assert cleaned is not None
    assert len(cleaned) == 1
    assert float(cleaned["Close"].iloc[-1]) == 100.5
    assert max_bar_date(df) == pd.Timestamp("2026-08-27").date()
    assert ohlcv_has_incomplete_last_bar(df) is True
    assert ohlcv_is_stale(df, max_age_days=5) is True


def test_validate_ohlcv_flags_nan_close():
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-08-27", "2026-08-28"]),
            "Close": [100.0, np.nan],
        }
    )
    result = validate_ohlcv(df)
    assert result.ok is False
    assert "nan_close" in result.issues
