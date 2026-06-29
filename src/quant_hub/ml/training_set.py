"""Build filtered training frames from Postgres labeled scan history."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from quant_hub.infrastructure.postgres.connection import get_connection
from quant_hub.ml.constants import LABEL_STATUS_OK, SWING_FEATURE_COLUMNS, SWING_SETUP_TIERS
from quant_hub.ml.features import extract_features, merge_outcome_columns

logger = logging.getLogger(__name__)


@dataclass
class TrainingSetStats:
    rows_raw: int = 0
    rows_after_tier: int = 0
    rows_after_label: int = 0
    rows_final: int = 0
    drop_tier: int = 0
    drop_label_status: int = 0
    drop_missing_target: int = 0
    drop_missing_features: int = 0

    def summary(self) -> str:
        return (
            f"raw={self.rows_raw} tier_ok={self.rows_after_tier} "
            f"label_ok={self.rows_after_label} final={self.rows_final} "
            f"drops[tier={self.drop_tier} label={self.drop_label_status} "
            f"target={self.drop_missing_target} features={self.drop_missing_features}]"
        )


@dataclass
class TrainingSetResult:
    frame: pd.DataFrame
    feature_columns: tuple[str, ...]
    stats: TrainingSetStats
    target_column: str = "label_binary"


def feature_columns_for_strategy(strategy_id: str) -> tuple[str, ...]:
    if strategy_id == "swing":
        return SWING_FEATURE_COLUMNS
    raise ValueError(f"No feature columns defined for strategy {strategy_id!r}")


def _parse_detail(detail: Any) -> dict[str, Any]:
    if isinstance(detail, str):
        return json.loads(detail)
    return detail or {}


def fetch_labeled_rows(
    *,
    strategy_id: str,
    universe_id: str,
    since: date | None,
    until: date | None,
    horizon_days: int,
) -> list[dict[str, Any]]:
    clauses = ["sr.strategy_id = %s", "sr.universe_id = %s"]
    params: list[Any] = [horizon_days, strategy_id, universe_id]
    if since:
        clauses.append("sr.scan_date >= %s")
        params.append(since)
    if until:
        clauses.append("sr.scan_date <= %s")
        params.append(until)
    where = " AND ".join(clauses)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT sr.id, sr.scan_date, sr.scan_time, sr.strategy_id, sr.universe_id,
                       sr.universe_size, sr.regime_label, sr.regime_multiplier, sr.metadata,
                       tr.ticker, tr.tier, tr.detail,
                       so.horizon_days, so.anchor_date, so.forward_return_pct,
                       so.forward_max_gain_pct, so.forward_max_drawdown_pct,
                       so.spy_forward_return_pct, so.excess_return_pct,
                       so.label_binary, so.label_status
                FROM scan_runs sr
                JOIN ticker_results tr ON tr.run_id = sr.id
                LEFT JOIN signal_outcomes so
                  ON so.run_id = sr.id AND so.ticker = tr.ticker
                 AND so.horizon_days = %s
                WHERE {where}
                ORDER BY sr.scan_date, tr.ticker
                """,
                params,
            )
            keys = [
                "run_id",
                "scan_date",
                "scan_time",
                "strategy_id",
                "universe_id",
                "universe_size",
                "regime_label",
                "regime_multiplier",
                "metadata",
                "ticker",
                "tier",
                "detail",
                "horizon_days",
                "anchor_date",
                "forward_return_pct",
                "forward_max_gain_pct",
                "forward_max_drawdown_pct",
                "spy_forward_return_pct",
                "excess_return_pct",
                "label_binary",
                "label_status",
            ]
            return [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]


def build_training_frame(
    *,
    strategy_id: str,
    universe_id: str,
    since: date | None = None,
    until: date | None = None,
    horizon_days: int = 10,
    setups_only: bool = True,
    label_status: str = LABEL_STATUS_OK,
    feature_columns: tuple[str, ...] | None = None,
) -> TrainingSetResult:
    """Load labeled features from Postgres and return a training-ready DataFrame."""
    feature_columns = feature_columns or feature_columns_for_strategy(strategy_id)
    stats = TrainingSetStats()
    raw_rows = fetch_labeled_rows(
        strategy_id=strategy_id,
        universe_id=universe_id,
        since=since,
        until=until,
        horizon_days=horizon_days,
    )
    stats.rows_raw = len(raw_rows)

    records: list[dict[str, Any]] = []
    for row in raw_rows:
        tier = row.get("tier") or ""
        if setups_only and tier not in SWING_SETUP_TIERS:
            stats.drop_tier += 1
            continue
        stats.rows_after_tier += 1

        status = row.get("label_status")
        if label_status and status != label_status:
            stats.drop_label_status += 1
            continue
        stats.rows_after_label += 1

        if row.get("label_binary") is None:
            stats.drop_missing_target += 1
            continue

        detail = _parse_detail(row.pop("detail"))
        run = {
            "id": row["run_id"],
            "scan_date": row["scan_date"],
            "scan_time": row.get("scan_time"),
            "strategy_id": row["strategy_id"],
            "universe_id": row["universe_id"],
            "universe_size": row.get("universe_size"),
            "regime_label": row.get("regime_label"),
            "regime_multiplier": row.get("regime_multiplier"),
            "metadata": row.get("metadata") or {},
        }
        features = extract_features(strategy_id=strategy_id, detail=detail, run=run)
        outcome = {
            "horizon_days": row.get("horizon_days"),
            "anchor_date": row.get("anchor_date"),
            "forward_return_pct": row.get("forward_return_pct"),
            "forward_max_gain_pct": row.get("forward_max_gain_pct"),
            "forward_max_drawdown_pct": row.get("forward_max_drawdown_pct"),
            "spy_forward_return_pct": row.get("spy_forward_return_pct"),
            "excess_return_pct": row.get("excess_return_pct"),
            "label_binary": row.get("label_binary"),
            "label_status": row.get("label_status"),
        }
        merged = merge_outcome_columns(features, outcome)
        merged["tier"] = tier
        merged["scan_date"] = str(row["scan_date"])
        records.append(merged)

    if not records:
        empty = pd.DataFrame(columns=[*feature_columns, "label_binary", "scan_date", "ticker", "run_id"])
        return TrainingSetResult(
            frame=empty,
            feature_columns=feature_columns,
            stats=stats,
        )

    df = pd.DataFrame(records)
    for col in feature_columns:
        if col not in df.columns:
            df[col] = None

    numeric = df[list(feature_columns)].apply(pd.to_numeric, errors="coerce")
    valid = numeric.notna().all(axis=1)
    stats.drop_missing_features = int((~valid).sum())
    df = df.loc[valid].copy()
    stats.rows_final = len(df)

    logger.info("Training set built: %s", stats.summary())
    return TrainingSetResult(
        frame=df,
        feature_columns=feature_columns,
        stats=stats,
    )


def split_features_target(
    result: TrainingSetResult,
    *,
    target_column: str = "label_binary",
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Return X, y, and metadata (scan_date, ticker, run_id, forward_return_pct, swing_score)."""
    df = result.frame
    meta_cols = [
        c
        for c in (
            "scan_date",
            "ticker",
            "run_id",
            "forward_return_pct",
            "swing_score",
            "tier",
        )
        if c in df.columns
    ]
    X = df[list(result.feature_columns)].astype(float)
    y = df[target_column].astype(int)
    meta = df[meta_cols].copy()
    return X, y, meta
