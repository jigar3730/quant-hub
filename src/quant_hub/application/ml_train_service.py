"""Train LightGBM models on labeled swing (or future strategy) features."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from quant_hub.config import FEATURE_SCHEMA_VERSION, ML_MODELS_DIR
from quant_hub.infrastructure.postgres.ml_models_repository import MlModelsRepository
from quant_hub.ml.constants import MODEL_TYPE_LIGHTGBM_CLASSIFIER
from quant_hub.ml.evaluate import EvalMetrics, evaluate_predictions
from quant_hub.ml.train import save_model_artifact, train_lightgbm_classifier
from quant_hub.ml.training_set import (
    TrainingSetResult,
    build_training_frame,
    split_features_target,
)
from quant_hub.ml.walk_forward import mask_by_dates, simple_holdout_split, unique_sorted_dates

logger = logging.getLogger(__name__)


@dataclass
class TrainRunStats:
    model_id: int | None = None
    model_name: str = ""
    artifact_path: str = ""
    train_rows: int = 0
    holdout_metrics: EvalMetrics | None = None
    training_set_stats: str = ""
    feature_importance: dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        parts = [
            f"model_id={self.model_id}",
            f"name={self.model_name}",
            f"train_rows={self.train_rows}",
        ]
        if self.holdout_metrics:
            parts.append(f"holdout[{self.holdout_metrics.summary()}]")
        return " ".join(parts)


class MLTrainService:
    def __init__(self, *, models_repo: MlModelsRepository | None = None) -> None:
        self.models_repo = models_repo or MlModelsRepository()

    def run(
        self,
        *,
        strategy_id: str,
        universe_id: str,
        since: date,
        until: date | None = None,
        horizon_days: int = 10,
        split_date: date | None = None,
        name: str | None = None,
        setups_only: bool = True,
        train_params: dict[str, Any] | None = None,
        top_k: int = 5,
    ) -> TrainRunStats:
        until = until or date.today()
        result = build_training_frame(
            strategy_id=strategy_id,
            universe_id=universe_id,
            since=since,
            until=until,
            horizon_days=horizon_days,
            setups_only=setups_only,
        )
        stats = TrainRunStats(training_set_stats=result.stats.summary())
        if result.frame.empty:
            logger.warning("Empty training set")
            return stats

        all_dates = unique_sorted_dates(result.frame["scan_date"])
        if split_date is None and len(all_dates) >= 26:
            split_date = all_dates[-26]
        elif split_date is None and len(all_dates) >= 2:
            split_date = all_dates[len(all_dates) // 2]

        X, y, meta = split_features_target(result)
        if split_date:
            train_dates, test_dates = simple_holdout_split(all_dates, split_date=split_date)
            train_mask = mask_by_dates(meta, train_dates)
            test_mask = mask_by_dates(meta, test_dates)
        else:
            train_mask = pd.Series(True, index=meta.index)
            test_mask = pd.Series(False, index=meta.index)

        X_train, y_train = X.loc[train_mask], y.loc[train_mask]
        if X_train.empty:
            raise ValueError("No training rows after split")

        booster = train_lightgbm_classifier(X_train, y_train, params=train_params)
        stats.train_rows = len(X_train)

        model_name = name or self._default_name(strategy_id, universe_id, horizon_days)
        artifact_dir = ML_MODELS_DIR / model_name
        model_path = save_model_artifact(
            booster,
            artifact_dir=artifact_dir,
            feature_columns=result.feature_columns,
            extra={
                "strategy_id": strategy_id,
                "universe_id": universe_id,
                "horizon_days": horizon_days,
            },
        )

        importance = booster.feature_importance(importance_type="gain")
        stats.feature_importance = {
            col: float(importance[i])
            for i, col in enumerate(result.feature_columns)
        }

        holdout_metrics: EvalMetrics | None = None
        if test_mask.any():
            y_score = pd.Series(booster.predict(X.loc[test_mask]), index=X.loc[test_mask].index)
            holdout_metrics = evaluate_predictions(
                y.loc[test_mask],
                y_score,
                meta.loc[test_mask],
                top_k=top_k,
            )
            stats.holdout_metrics = holdout_metrics

        metrics_payload = {
            "train_rows": stats.train_rows,
            "feature_importance": stats.feature_importance,
            "training_set": result.stats.summary(),
        }
        if holdout_metrics:
            metrics_payload["holdout"] = holdout_metrics.to_dict()

        if split_date:
            train_since = min(train_dates)
            train_until = max(train_dates)
        else:
            train_since = since
            train_until = until

        model_id = self.models_repo.insert_model(
            name=model_name,
            strategy_id=strategy_id,
            universe_id=universe_id,
            horizon_days=horizon_days,
            feature_schema_version=FEATURE_SCHEMA_VERSION,
            model_type=MODEL_TYPE_LIGHTGBM_CLASSIFIER,
            artifact_path=str(model_path.parent),
            train_params=train_params or {},
            metrics=metrics_payload,
            feature_columns=list(result.feature_columns),
            train_since=train_since,
            train_until=train_until,
            eval_split_date=split_date,
        )
        stats.model_id = model_id
        stats.model_name = model_name
        stats.artifact_path = str(model_path.parent)
        logger.info("Train complete: %s", stats.summary())
        return stats

    @staticmethod
    def _default_name(strategy_id: str, universe_id: str, horizon_days: int) -> str:
        stamp = date.today().isoformat().replace("-", "")
        return f"{strategy_id}_{universe_id}_h{horizon_days}_{stamp}"
