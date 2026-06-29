"""Unit tests for training set filters and feature leakage guards."""

from __future__ import annotations

from quant_hub.ml.constants import SWING_FEATURE_COLUMNS, SWING_SETUP_TIERS
from quant_hub.ml.training_set import split_features_target
from quant_hub.ml.training_set import TrainingSetResult
import pandas as pd


def test_swing_feature_columns_exclude_leakage():
    forbidden = {
        "forward_return_pct",
        "forward_max_gain_pct",
        "label_binary",
        "label_status",
        "run_id",
        "scan_date",
        "scan_time",
        "ticker",
    }
    assert forbidden.isdisjoint(set(SWING_FEATURE_COLUMNS))


def test_split_features_target_returns_meta_for_baseline():
    df = pd.DataFrame(
        {
            **{col: [1.0, 2.0] for col in SWING_FEATURE_COLUMNS},
            "label_binary": [0, 1],
            "scan_date": ["2024-01-05", "2024-01-12"],
            "ticker": ["AAPL", "MSFT"],
            "run_id": [1, 2],
            "forward_return_pct": [1.5, -0.5],
            "swing_score": [80.0, 60.0],
            "tier": ["SETUP_LONG", "SETUP_SHORT"],
        }
    )
    result = TrainingSetResult(frame=df, feature_columns=SWING_FEATURE_COLUMNS, stats=None)  # type: ignore[arg-type]
    X, y, meta = split_features_target(result)
    assert list(X.columns) == list(SWING_FEATURE_COLUMNS)
    assert y.tolist() == [0, 1]
    assert "swing_score" in meta.columns
    assert "forward_return_pct" in meta.columns


def test_setup_tiers_only_setups():
    assert "SETUP_LONG" in SWING_SETUP_TIERS
    assert "SETUP_SHORT" in SWING_SETUP_TIERS
    assert "WATCH" not in SWING_SETUP_TIERS
