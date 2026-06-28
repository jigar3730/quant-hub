import numpy as np
import pandas as pd

from quant_hub.strategies.swing.scanner import add_indicators, evaluate_setup, scan_ticker


def _synthetic_uptrend_weeks(n: int = 120) -> pd.DataFrame:
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="W-FRI")
    close = np.linspace(100, 150, n) + np.random.default_rng(0).normal(0, 0.5, n)
    close[-1] = close[-2] * 1.005  # slight pullback to EMA zone
    high = close + 1
    low = close - 1
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": np.full(n, 1_000_000),
        }
    )


def test_add_indicators_produces_columns():
    df = add_indicators(_synthetic_uptrend_weeks(80))
    for col in ("EMA20", "EMA50", "MACD_Hist", "RSI", "ATR"):
        assert col in df.columns
    assert len(df) >= 20


def test_scan_ticker_insufficient_data():
    df = _synthetic_uptrend_weeks(30)
    assert scan_ticker(df, "TEST", min_bars=60) is None


def test_evaluate_setup_returns_none_on_flat_data():
    n = 120
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="W-FRI")
    flat = pd.DataFrame(
        {
            "Date": dates,
            "Open": [100.0] * n,
            "High": [101.0] * n,
            "Low": [99.0] * n,
            "Close": [100.0] * n,
            "Volume": [1_000_000] * n,
        }
    )
    enriched = add_indicators(flat)
    if len(enriched) >= 2:
        assert evaluate_setup(enriched) is None
