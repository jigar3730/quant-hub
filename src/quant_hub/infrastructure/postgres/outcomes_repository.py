"""Postgres persistence for ML signal outcomes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from quant_hub.infrastructure.postgres.connection import get_connection

logger = logging.getLogger(__name__)


class OutcomesRepository:
    def upsert_outcomes(
        self,
        *,
        run_id: int,
        ticker: str,
        rows: list[dict[str, Any]],
    ) -> int:
        if not rows:
            return 0
        computed_at = datetime.now(timezone.utc)
        with get_connection() as conn:
            with conn.cursor() as cur:
                for row in rows:
                    cur.execute(
                        """
                        INSERT INTO signal_outcomes (
                            run_id, ticker, horizon_days, anchor_date,
                            forward_return_pct, forward_max_gain_pct,
                            forward_max_drawdown_pct, spy_forward_return_pct,
                            excess_return_pct, label_binary, label_status, computed_at
                        ) VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (run_id, ticker, horizon_days)
                        DO UPDATE SET
                            anchor_date = EXCLUDED.anchor_date,
                            forward_return_pct = EXCLUDED.forward_return_pct,
                            forward_max_gain_pct = EXCLUDED.forward_max_gain_pct,
                            forward_max_drawdown_pct = EXCLUDED.forward_max_drawdown_pct,
                            spy_forward_return_pct = EXCLUDED.spy_forward_return_pct,
                            excess_return_pct = EXCLUDED.excess_return_pct,
                            label_binary = EXCLUDED.label_binary,
                            label_status = EXCLUDED.label_status,
                            computed_at = EXCLUDED.computed_at
                        """,
                        (
                            run_id,
                            ticker,
                            row["horizon_days"],
                            row["anchor_date"],
                            row.get("forward_return_pct"),
                            row.get("forward_max_gain_pct"),
                            row.get("forward_max_drawdown_pct"),
                            row.get("spy_forward_return_pct"),
                            row.get("excess_return_pct"),
                            row.get("label_binary"),
                            row["label_status"],
                            computed_at,
                        ),
                    )
            conn.commit()
        return len(rows)

    def count_by_status(self) -> dict[str, int]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT label_status, COUNT(*)::int
                    FROM signal_outcomes
                    GROUP BY label_status
                    ORDER BY label_status
                    """
                )
                return {row[0]: row[1] for row in cur.fetchall()}

    def list_outcomes_for_run(
        self,
        run_id: int,
        *,
        horizon_days: int | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["run_id = %s"]
        params: list[Any] = [run_id]
        if horizon_days is not None:
            clauses.append("horizon_days = %s")
            params.append(horizon_days)
        where = " AND ".join(clauses)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT run_id, ticker, horizon_days, anchor_date,
                           forward_return_pct, forward_max_gain_pct,
                           forward_max_drawdown_pct, spy_forward_return_pct,
                           excess_return_pct, label_binary, label_status, computed_at
                    FROM signal_outcomes
                    WHERE {where}
                    """,
                    params,
                )
                keys = [
                    "run_id",
                    "ticker",
                    "horizon_days",
                    "anchor_date",
                    "forward_return_pct",
                    "forward_max_gain_pct",
                    "forward_max_drawdown_pct",
                    "spy_forward_return_pct",
                    "excess_return_pct",
                    "label_binary",
                    "label_status",
                    "computed_at",
                ]
                return [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]

    def outcome_map_for_run(self, run_id: int, *, horizon_days: int) -> dict[str, dict]:
        rows = self.list_outcomes_for_run(run_id, horizon_days=horizon_days)
        return {r["ticker"]: r for r in rows}

    def count_total(self) -> int:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM signal_outcomes")
                return int(cur.fetchone()[0])
