"""Unit tests for fine-grained swing scoring."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_hub.strategies.swing.scanner import add_indicators, analyze_swing
from quant_hub.strategies.swing.scoring import SWING_MAX_PENALTY, quality_label


def _synthetic_uptrend_weeks(n: int = 120) -> pd.DataFrame:
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="W-FRI")
    close = np.linspace(100, 150, n) + np.random.default_rng(0).normal(0, 0.5, n)
    close[-1] = close[-2] * 1.005
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": np.full(n, 1_000_000),
        }
    )


def test_partial_pullback_scores_below_full_setup():
    df = _synthetic_uptrend_weeks(120).copy()
    df.iloc[-1, df.columns.get_loc("Close")] = float(df.iloc[-1]["Close"]) * 1.12
    analysis = analyze_swing(df, "TEST", min_bars=60)
    result = analysis.score_result
    assert result is not None
    assert analysis.setup is None
    assert result.base_score < 100
    assert result.base_score > 0
    assert 0 <= result.swing_score <= 100


def test_penalties_reduce_score():
    df = _synthetic_uptrend_weeks(120).copy()
    df.iloc[-1, df.columns.get_loc("Close")] = float(df.iloc[-1]["Close"]) * 1.15
    analysis = analyze_swing(df, "TEST", min_bars=60)
    result = analysis.score_result
    assert result is not None
    assert result.penalties
    assert result.penalty_total < 0
    assert result.swing_score <= result.base_score
    assert abs(result.penalty_total) <= SWING_MAX_PENALTY


def test_quality_labels():
    assert quality_label(90).startswith("A")
    assert quality_label(75).startswith("B")
    assert quality_label(60).startswith("C")
    assert quality_label(40).startswith("D")
