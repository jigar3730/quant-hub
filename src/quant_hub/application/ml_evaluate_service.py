"""Evaluate registered ML models with walk-forward or holdout metrics."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from quant_hub.infrastructure.postgres.ml_models_repository import MlModelsRepository
from quant_hub.ml.evaluate import EvalMetrics, aggregate_fold_metrics, evaluate_predictions
from quant_hub.ml.train import load_model_artifact
from quant_hub.ml.training_set import build_training_frame, split_features_target
from quant_hub.ml.walk_forward import iter_walk_forward_folds, mask_by_dates, unique_sorted_dates

logger = logging.getLogger(__name__)


@dataclass
class EvaluateRunStats:
    model_id: int | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    fold_summaries: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if "mean_auc" in self.metrics:
            return (
                f"model_id={self.model_id} folds={self.metrics.get('n_folds', 0)} "
                f"mean_auc={self.metrics.get('mean_auc', 0):.4f} "
                f"mean_return_lift={self.metrics.get('mean_return_lift_vs_baseline', 0):.2f}"
            )
        holdout = self.metrics.get("holdout", {})
        return f"model_id={self.model_id} {holdout}"


class MLEvaluateService:
    def __init__(self, *, models_repo: MlModelsRepository | None = None) -> None:
        self.models_repo = models_repo or MlModelsRepository()

    def run(
        self,
        *,
        model_id: int | None = None,
        artifact_path: str | None = None,
        since: date | None = None,
        until: date | None = None,
        walk_forward: bool = False,
        train_weeks: int = 52,
        test_weeks: int = 13,
        top_k: int = 5,
        persist_metrics: bool = True,
    ) -> EvaluateRunStats:
        if model_id is not None:
            record = self.models_repo.get_by_id(model_id)
            if not record:
                raise ValueError(f"Model id {model_id} not found")
            artifact_path = record["artifact_path"]
            strategy_id = record["strategy_id"]
            universe_id = record["universe_id"]
            horizon_days = record["horizon_days"]
        elif artifact_path:
            from pathlib import Path

            meta_path = Path(artifact_path) / "features.json"
            meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
            strategy_id = meta.get("strategy_id", "swing")
            universe_id = meta.get("universe_id", "sp500")
            horizon_days = int(meta.get("horizon_days", 10))
            record = None
        else:
            raise ValueError("Specify --model-id or --artifact-path")

        booster, feature_columns = load_model_artifact(artifact_path)
        since = since or (date.fromisoformat(record["train_since"]) if record and record.get("train_since") else None)
        until = until or date.today()

        result = build_training_frame(
            strategy_id=strategy_id,
            universe_id=universe_id,
            since=since,
            until=until,
            horizon_days=horizon_days,
            setups_only=True,
        )
        if result.frame.empty:
            return EvaluateRunStats(model_id=model_id, metrics={"error": "empty dataset"})

        X, y, meta = split_features_target(result)
        X = X[list(feature_columns)].astype(float)

        stats = EvaluateRunStats(model_id=model_id)

        if walk_forward:
            folds = iter_walk_forward_folds(
                unique_sorted_dates(result.frame["scan_date"]),
                train_weeks=train_weeks,
                test_weeks=test_weeks,
            )
            fold_metrics: list[EvalMetrics] = []
            for fold in folds:
                test_mask = mask_by_dates(meta, fold.test_dates)
                if not test_mask.any():
                    continue
                y_score = pd.Series(booster.predict(X.loc[test_mask]), index=X.loc[test_mask].index)
                fm = evaluate_predictions(y.loc[test_mask], y_score, meta.loc[test_mask], top_k=top_k)
                fold_metrics.append(fm)
                stats.fold_summaries.append(f"split={fold.split_date} {fm.summary()}")
            stats.metrics = aggregate_fold_metrics(fold_metrics)
        else:
            split_date = None
            if record and record.get("eval_split_date"):
                split_date = date.fromisoformat(record["eval_split_date"])
            if split_date:
                test_mask = meta["scan_date"].astype(str) >= str(split_date)
            else:
                test_mask = pd.Series(True, index=meta.index)

            y_score = pd.Series(booster.predict(X.loc[test_mask]), index=X.loc[test_mask].index)
            holdout = evaluate_predictions(y.loc[test_mask], y_score, meta.loc[test_mask], top_k=top_k)
            stats.metrics = {"holdout": holdout.to_dict(), "n_samples": holdout.n_samples}

        if persist_metrics and model_id is not None and record:
            merged = dict(record.get("metrics") or {})
            merged["evaluation"] = stats.metrics
            if stats.fold_summaries:
                merged["fold_summaries"] = stats.fold_summaries
            self.models_repo.update_metrics(model_id, merged)

        logger.info("Evaluate complete: %s", stats.summary())
        return stats
