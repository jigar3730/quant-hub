from quant_hub.strategies.mean_reversion.scanner import add_indicators, analyze_ticker
from tests.unit.mean_reversion_helpers import synthetic_daily_bars, synthetic_long_setup_df


def test_add_indicators_produces_required_columns():
    df = synthetic_daily_bars(600)
    enriched = add_indicators(df)
    for col in ("EMA500", "BB_Upper", "BB_Mid", "BB_Lower", "RSI", "ATR"):
        assert col in enriched.columns
    assert len(enriched) >= 520


def test_analyze_ticker_returns_score_result():
    df = synthetic_long_setup_df()
    analysis = analyze_ticker(df, "SPY", min_bars=520, rs_percentile=0.7)
    assert analysis.fail_reason is None
    assert analysis.score_result is not None
    assert analysis.close > 0
    assert analysis.ema500 > 0


def test_analyze_ticker_insufficient_data():
    df = synthetic_daily_bars(200)
    analysis = analyze_ticker(df, "SPY", min_bars=520)
    assert analysis.fail_reason == "insufficient_data"
