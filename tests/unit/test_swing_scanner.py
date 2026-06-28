import numpy as np
import pandas as pd

from quant_hub.strategies.swing.scanner import (
    add_indicators,
    analyze_swing,
    evaluate_setup,
    scan_ticker,
)


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


def test_analyze_swing_returns_full_indicators_without_setup():
    df = _synthetic_uptrend_weeks(120).copy()
    # Price too far above EMA20 — fails pullback zone, but indicators still computed.
    df.iloc[-1, df.columns.get_loc("Close")] = float(df.iloc[-1]["Close"]) * 1.12
    analysis = analyze_swing(df, "TEST", min_bars=60)
    assert analysis.setup is None
    assert analysis.fail_reason == "no_setup"
    assert analysis.rsi is not None
    assert analysis.ema20 is not None
    assert len(analysis.long_checks) == 5
    assert len(analysis.short_checks) == 5


def test_analysis_to_report_includes_checks():
    from quant_hub.strategies.swing.scanner import analysis_to_report, analyze_swing

    df = _synthetic_uptrend_weeks(120).copy()
    df.iloc[-1, df.columns.get_loc("Close")] = float(df.iloc[-1]["Close"]) * 1.12
    analysis = analyze_swing(df, "TEST", min_bars=60)
    report = analysis_to_report(analysis)
    assert report["setup_detail"]["rsi"] is not None
    assert report["swing_checks"]
    assert report["eligibility"]["checks"]
    assert report["summary"]["swing_score"] == analysis.score_result.swing_score
    assert report["setup_detail"]["rule_breakdown"]
    assert "base_score" in report["setup_detail"]
    assert "penalties" in report["setup_detail"]


def test_compute_swing_score_uses_cached_result():
    from quant_hub.strategies.swing.scoring import compute_swing_score

    df = _synthetic_uptrend_weeks(120).copy()
    df.iloc[-1, df.columns.get_loc("Close")] = float(df.iloc[-1]["Close"]) * 1.12
    analysis = analyze_swing(df, "TEST", min_bars=60)
    assert compute_swing_score(analysis) == analysis.score_result.swing_score
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
