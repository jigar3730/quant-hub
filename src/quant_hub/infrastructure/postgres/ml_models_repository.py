"""Postgres persistence for trained ML models (Phase 2 registry)."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from quant_hub.infrastructure.postgres.connection import get_connection
from quant_hub.serialization.json_util import json_dumps

logger = logging.getLogger(__name__)


class MlModelsRepository:
    def insert_model(
        self,
        *,
        name: str,
        strategy_id: str,
        universe_id: str,
        horizon_days: int,
        feature_schema_version: str,
        model_type: str,
        artifact_path: str,
        train_params: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        feature_columns: list[str] | None = None,
        train_since: date | None = None,
        train_until: date | None = None,
        eval_split_date: date | None = None,
        status: str = "active",
    ) -> int:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ml_models (
                        name, strategy_id, universe_id, horizon_days,
                        feature_schema_version, model_type, train_params,
                        metrics, feature_columns, artifact_path,
                        train_since, train_until, eval_split_date, status
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s, %s
                    )
                    RETURNING id
                    """,
                    (
                        name,
                        strategy_id,
                        universe_id,
                        horizon_days,
                        feature_schema_version,
                        model_type,
                        json_dumps(train_params or {}),
                        json_dumps(metrics or {}),
                        json_dumps(feature_columns or []),
                        artifact_path,
                        train_since,
                        train_until,
                        eval_split_date,
                        status,
                    ),
                )
                model_id = cur.fetchone()[0]
            conn.commit()
            logger.info("Registered ml_model id=%s name=%s", model_id, name)
            return model_id

    def update_metrics(self, model_id: int, metrics: dict[str, Any]) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ml_models SET metrics = %s::jsonb WHERE id = %s
                    """,
                    (json_dumps(metrics), model_id),
                )
            conn.commit()

    def get_by_id(self, model_id: int) -> dict[str, Any] | None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, strategy_id, universe_id, horizon_days,
                           feature_schema_version, model_type, train_params,
                           metrics, feature_columns, artifact_path,
                           train_since, train_until, eval_split_date,
                           status, created_at
                    FROM ml_models WHERE id = %s
                    """,
                    (model_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return self._row_to_dict(row)

    def get_by_name(self, name: str) -> dict[str, Any] | None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, strategy_id, universe_id, horizon_days,
                           feature_schema_version, model_type, train_params,
                           metrics, feature_columns, artifact_path,
                           train_since, train_until, eval_split_date,
                           status, created_at
                    FROM ml_models WHERE name = %s
                    """,
                    (name,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return self._row_to_dict(row)

    def list_models(
        self,
        *,
        strategy_id: str | None = None,
        universe_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if strategy_id:
            clauses.append("strategy_id = %s")
            params.append(strategy_id)
        if universe_id:
            clauses.append("universe_id = %s")
            params.append(universe_id)
        if status:
            clauses.append("status = %s")
            params.append(status)
        where = " AND ".join(clauses) if clauses else "TRUE"
        params.append(limit)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, name, strategy_id, universe_id, horizon_days,
                           feature_schema_version, model_type, train_params,
                           metrics, feature_columns, artifact_path,
                           train_since, train_until, eval_split_date,
                           status, created_at
                    FROM ml_models
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    params,
                )
                return [self._row_to_dict(row) for row in cur.fetchall()]

    def _row_to_dict(self, row: tuple) -> dict[str, Any]:
        keys = [
            "id",
            "name",
            "strategy_id",
            "universe_id",
            "horizon_days",
            "feature_schema_version",
            "model_type",
            "train_params",
            "metrics",
            "feature_columns",
            "artifact_path",
            "train_since",
            "train_until",
            "eval_split_date",
            "status",
            "created_at",
        ]
        data = dict(zip(keys, row, strict=True))
        if isinstance(data.get("created_at"), datetime):
            data["created_at"] = data["created_at"].isoformat()
        for dkey in ("train_since", "train_until", "eval_split_date"):
            if data.get(dkey) is not None:
                data[dkey] = str(data[dkey])
        return data
