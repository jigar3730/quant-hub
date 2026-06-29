"""LightGBM training helpers (Phase 2)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_LGBM_PARAMS: dict[str, Any] = {
    "objective": "binary",
    "metric": "auc",
    "verbosity": -1,
    "num_leaves": 15,
    "learning_rate": 0.05,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "min_child_samples": 5,
    "seed": 42,
}


def train_lightgbm_classifier(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    import lightgbm as lgb

    merged = {**DEFAULT_LGBM_PARAMS, **(params or {})}
    train_data = lgb.Dataset(X, label=y)
    booster = lgb.train(
        merged,
        train_data,
        num_boost_round=int(merged.pop("num_boost_round", 100)),
    )
    return booster


def save_model_artifact(
    booster: Any,
    *,
    artifact_dir: Path,
    feature_columns: tuple[str, ...],
    extra: dict[str, Any] | None = None,
) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "model.txt"
    booster.save_model(str(model_path))
    meta = {
        "feature_columns": list(feature_columns),
        **(extra or {}),
    }
    (artifact_dir / "features.json").write_text(json.dumps(meta, indent=2))
    logger.info("Saved model artifact to %s", artifact_dir)
    return model_path


def load_model_artifact(artifact_dir: Path | str) -> tuple[Any, list[str]]:
    import lightgbm as lgb

    path = Path(artifact_dir)
    booster = lgb.Booster(model_file=str(path / "model.txt"))
    meta = json.loads((path / "features.json").read_text())
    return booster, list(meta["feature_columns"])
