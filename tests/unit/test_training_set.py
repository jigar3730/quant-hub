"""Unit tests for training set filters and feature leakage guards."""

from __future__ import annotations

import pandas as pd

from quant_hub.ml.constants import LAUNCHPAD_FEATURE_COLUMNS, LAUNCHPAD_SETUP_TIERS
from quant_hub.ml.training_set import TrainingSetResult, split_features_target


def test_launchpad_feature_columns_exclude_leakage():
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
    assert forbidden.isdisjoint(set(LAUNCHPAD_FEATURE_COLUMNS))


def test_split_features_target_returns_meta_for_baseline():
    df = pd.DataFrame(
        {
            **{col: [1.0, 2.0] for col in LAUNCHPAD_FEATURE_COLUMNS},
            "label_binary": [0, 1],
            "scan_date": ["2024-01-05", "2024-01-12"],
            "ticker": ["AAPL", "MSFT"],
            "run_id": [1, 2],
            "forward_return_pct": [1.5, -0.5],
            "final_score": [80.0, 60.0],
            "tier": ["Tier 1", "Tier 2"],
        }
    )
    result = TrainingSetResult(frame=df, feature_columns=LAUNCHPAD_FEATURE_COLUMNS, stats=None)  # type: ignore[arg-type]
    X, y, meta = split_features_target(result)
    assert list(X.columns) == list(LAUNCHPAD_FEATURE_COLUMNS)
    assert y.tolist() == [0, 1]
    assert "final_score" in meta.columns
    assert "forward_return_pct" in meta.columns


def test_setup_tiers_only_setups():
    assert "Tier 1" in LAUNCHPAD_SETUP_TIERS
    assert "Tier 2" in LAUNCHPAD_SETUP_TIERS
    assert "WATCH" not in LAUNCHPAD_SETUP_TIERS
