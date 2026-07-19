"""Model evaluation metrics and walk-forward score-baseline comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class EvalMetrics:
    n_samples: int = 0
    n_weeks: int = 0
    auc: float | None = None
    precision_at_k: float | None = None
    recall_at_k: float | None = None
    mean_forward_return_top_k: float | None = None
    baseline_score_top_k_return: float | None = None
    top_k: int = 5
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_samples": self.n_samples,
            "n_weeks": self.n_weeks,
            "auc": self.auc,
            "precision_at_k": self.precision_at_k,
            "recall_at_k": self.recall_at_k,
            f"mean_forward_return_top_{self.top_k}": self.mean_forward_return_top_k,
            f"baseline_score_top_{self.top_k}_return": self.baseline_score_top_k_return,
            **self.extra,
        }

    def summary(self) -> str:
        parts = [f"n={self.n_samples}", f"weeks={self.n_weeks}"]
        if self.auc is not None:
            parts.append(f"auc={self.auc:.4f}")
        if self.mean_forward_return_top_k is not None:
            parts.append(f"ml_top{self.top_k}_ret={self.mean_forward_return_top_k:.2f}%")
        if self.baseline_score_top_k_return is not None:
            parts.append(f"score_top{self.top_k}_ret={self.baseline_score_top_k_return:.2f}%")
        return " ".join(parts)


def _safe_auc(y_true: pd.Series, y_score: pd.Series) -> float | None:
    if y_true.nunique() < 2:
        return None
    try:
        from sklearn.metrics import roc_auc_score

        return float(roc_auc_score(y_true, y_score))
    except ValueError:
        return None


def _top_k_per_week_returns(
    meta: pd.DataFrame,
    scores: pd.Series,
    *,
    top_k: int,
    return_col: str = "forward_return_pct",
) -> float | None:
    if return_col not in meta.columns:
        return None
    df = meta.copy()
    df["_score"] = scores.values
    df = df.dropna(subset=["_score", return_col])
    if df.empty:
        return None

    weekly_returns: list[float] = []
    for _, group in df.groupby("scan_date"):
        top = group.nlargest(min(top_k, len(group)), "_score")
        weekly_returns.append(float(top[return_col].mean()))
    if not weekly_returns:
        return None
    return float(np.mean(weekly_returns))


def evaluate_predictions(
    y_true: pd.Series,
    y_score: pd.Series,
    meta: pd.DataFrame,
    *,
    top_k: int = 5,
) -> EvalMetrics:
    """Compute AUC and top-K weekly forward-return metrics vs raw score baseline."""
    metrics = EvalMetrics(n_samples=len(y_true), top_k=top_k)
    if "scan_date" in meta.columns:
        metrics.n_weeks = int(meta["scan_date"].nunique())

    metrics.auc = _safe_auc(y_true, y_score)
    metrics.mean_forward_return_top_k = _top_k_per_week_returns(meta, y_score, top_k=top_k)

    baseline_column = next(
        (
            column
            for column in ("final_score", "normalized_score")
            if column in meta.columns
        ),
        None,
    )
    if baseline_column is not None:
        baseline_scores = pd.to_numeric(meta[baseline_column], errors="coerce")
        metrics.baseline_score_top_k_return = _top_k_per_week_returns(meta, baseline_scores, top_k=top_k)

    try:
        from sklearn.metrics import precision_score, recall_score

        y_pred = (y_score >= 0.5).astype(int)
        metrics.precision_at_k = float(precision_score(y_true, y_pred, zero_division=0))
        metrics.recall_at_k = float(recall_score(y_true, y_pred, zero_division=0))
    except ImportError:
        pass

    if (
        metrics.mean_forward_return_top_k is not None
        and metrics.baseline_score_top_k_return is not None
    ):
        metrics.extra["return_lift_vs_baseline"] = (
            metrics.mean_forward_return_top_k - metrics.baseline_score_top_k_return
        )

    return metrics


def aggregate_fold_metrics(fold_metrics: list[EvalMetrics]) -> dict[str, Any]:
    """Average numeric metrics across walk-forward folds."""
    if not fold_metrics:
        return {}
    keys = ("auc", "mean_forward_return_top_k", "baseline_score_top_k_return")
    out: dict[str, Any] = {"n_folds": len(fold_metrics)}
    for key in keys:
        vals = [getattr(m, key) for m in fold_metrics if getattr(m, key) is not None]
        if vals:
            out[f"mean_{key}"] = float(np.mean(vals))
    lifts = [m.extra.get("return_lift_vs_baseline") for m in fold_metrics if m.extra.get("return_lift_vs_baseline") is not None]
    if lifts:
        out["mean_return_lift_vs_baseline"] = float(np.mean(lifts))
    return out
