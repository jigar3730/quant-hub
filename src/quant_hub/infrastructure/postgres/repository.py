from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any

from quant_hub.infrastructure.postgres.connection import get_connection

logger = logging.getLogger(__name__)


class ScanRepository:
    def upsert_scan(
        self,
        *,
        scan_date: date,
        strategy_id: str,
        universe_id: str,
        report: dict,
        scan_time: datetime | None = None,
    ) -> int:
        summary = report["scan_summary"]
        regime = report["market_regime"]
        tiers = summary["tier_counts"]
        scan_time = scan_time or datetime.now(timezone.utc)

        metadata = {
            "filter_breakdown": summary.get("filter_breakdown", {}),
            "eligible_count": summary.get("eligible_count"),
            "excluded_count": summary.get("excluded_count"),
            "spy_price": regime.get("spy_price"),
            "return_63d_pct": regime.get("return_63d_pct"),
        }

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scan_runs (
                        scan_date, scan_time, strategy_id, universe_id,
                        universe_size, tier1_count, tier2_count, tier3_count,
                        filtered_count, actionable_count,
                        regime_label, regime_multiplier, metadata
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s::jsonb
                    )
                    ON CONFLICT (scan_date, strategy_id, universe_id)
                    DO UPDATE SET
                        scan_time = EXCLUDED.scan_time,
                        universe_size = EXCLUDED.universe_size,
                        tier1_count = EXCLUDED.tier1_count,
                        tier2_count = EXCLUDED.tier2_count,
                        tier3_count = EXCLUDED.tier3_count,
                        filtered_count = EXCLUDED.filtered_count,
                        actionable_count = EXCLUDED.actionable_count,
                        regime_label = EXCLUDED.regime_label,
                        regime_multiplier = EXCLUDED.regime_multiplier,
                        metadata = EXCLUDED.metadata
                    RETURNING id
                    """,
                    (
                        scan_date,
                        scan_time,
                        strategy_id,
                        universe_id,
                        summary.get("universe_size"),
                        tiers.get("Tier 1", 0),
                        tiers.get("Tier 2", 0),
                        tiers.get("Tier 3", 0),
                        tiers.get("filtered", 0),
                        summary.get("actionable_count", 0),
                        regime.get("label"),
                        regime.get("multiplier"),
                        json.dumps(metadata),
                    ),
                )
                run_id = cur.fetchone()[0]

                cur.execute("DELETE FROM ticker_results WHERE run_id = %s", (run_id,))

                rows = []
                for ticker in report.get("tickers", []):
                    summary_row = ticker.get("summary") or {}
                    rows.append(
                        (
                            run_id,
                            ticker["ticker"],
                            ticker.get("eligible"),
                            ticker.get("tier"),
                            ticker.get("sector_etf"),
                            summary_row.get("final_adjusted_score"),
                            (ticker.get("eligibility") or {}).get("fail_reason"),
                            json.dumps(ticker),
                        )
                    )

                if rows:
                    cur.executemany(
                        """
                        INSERT INTO ticker_results (
                            run_id, ticker, eligible, tier, sector_etf,
                            final_score, filter_reason, detail
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        """,
                        rows,
                    )

            conn.commit()
            logger.info(
                "Persisted scan run_id=%s strategy=%s universe=%s tickers=%d",
                run_id,
                strategy_id,
                universe_id,
                len(rows),
            )
            return run_id

    def get_latest_run(
        self,
        *,
        strategy_id: str = "breakout",
        universe_id: str | None = None,
        scan_date: date | None = None,
    ) -> dict[str, Any] | None:
        clauses = ["strategy_id = %s"]
        params: list[Any] = [strategy_id]
        if universe_id:
            clauses.append("universe_id = %s")
            params.append(universe_id)
        if scan_date:
            clauses.append("scan_date = %s")
            params.append(scan_date)

        where = " AND ".join(clauses)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, scan_date, scan_time, strategy_id, universe_id,
                           universe_size, tier1_count, tier2_count, tier3_count,
                           filtered_count, actionable_count,
                           regime_label, regime_multiplier, metadata
                    FROM scan_runs
                    WHERE {where}
                    ORDER BY scan_date DESC, scan_time DESC
                    LIMIT 1
                    """,
                    params,
                )
                row = cur.fetchone()
                if not row:
                    return None
                return self._row_to_run_dict(row)

    def load_report(
        self,
        *,
        strategy_id: str = "breakout",
        universe_id: str | None = None,
        scan_date: date | None = None,
    ) -> dict[str, Any] | None:
        run = self.get_latest_run(
            strategy_id=strategy_id,
            universe_id=universe_id,
            scan_date=scan_date,
        )
        if not run:
            return None

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT detail FROM ticker_results
                    WHERE run_id = %s
                    ORDER BY ticker
                    """,
                    (run["id"],),
                )
                tickers = []
                for row in cur.fetchall():
                    detail = row[0]
                    if isinstance(detail, str):
                        detail = json.loads(detail)
                    tickers.append(detail)

        metadata = run.get("metadata") or {}
        tier_counts = {
            "Tier 1": run.get("tier1_count", 0),
            "Tier 2": run.get("tier2_count", 0),
            "Tier 3": run.get("tier3_count", 0),
            "filtered": run.get("filtered_count", 0),
        }
        return {
            "strategy_id": run["strategy_id"],
            "universe_id": run["universe_id"],
            "scan_date": str(run["scan_date"]),
            "scan_time": run["scan_time"].isoformat() if run["scan_time"] else None,
            "scan_summary": {
                "universe_size": run.get("universe_size", len(tickers)),
                "eligible_count": metadata.get("eligible_count", 0),
                "excluded_count": metadata.get("excluded_count", 0),
                "tier_counts": tier_counts,
                "actionable_count": run.get("actionable_count", 0),
                "filter_breakdown": metadata.get("filter_breakdown", {}),
            },
            "market_regime": {
                "label": run.get("regime_label", "unknown"),
                "multiplier": run.get("regime_multiplier", 1.0),
                "spy_price": metadata.get("spy_price"),
                "return_63d_pct": metadata.get("return_63d_pct"),
            },
            "tickers": tickers,
        }

    def list_runs(
        self,
        *,
        strategy_id: str = "breakout",
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, scan_date, scan_time, strategy_id, universe_id,
                           universe_size, tier1_count, tier2_count, tier3_count,
                           filtered_count, actionable_count,
                           regime_label, regime_multiplier, metadata
                    FROM scan_runs
                    WHERE strategy_id = %s
                    ORDER BY scan_date DESC, scan_time DESC
                    LIMIT %s
                    """,
                    (strategy_id, limit),
                )
                return [self._row_to_run_dict(row) for row in cur.fetchall()]

    def table_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        with get_connection() as conn:
            with conn.cursor() as cur:
                for table in ("scan_runs", "ticker_results", "job_runs"):
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    counts[table] = cur.fetchone()[0]
        return counts

    @staticmethod
    def _row_to_run_dict(row: tuple) -> dict[str, Any]:
        keys = [
            "id",
            "scan_date",
            "scan_time",
            "strategy_id",
            "universe_id",
            "universe_size",
            "tier1_count",
            "tier2_count",
            "tier3_count",
            "filtered_count",
            "actionable_count",
            "regime_label",
            "regime_multiplier",
            "metadata",
        ]
        data = dict(zip(keys, row, strict=True))
        if isinstance(data.get("metadata"), str):
            data["metadata"] = json.loads(data["metadata"])
        return data


class JobRunRepository:
    def start_job(self, job_name: str, *, tickers_requested: int = 0) -> int:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO job_runs (job_name, started_at, status, tickers_requested)
                    VALUES (%s, NOW(), 'running', %s)
                    RETURNING id
                    """,
                    (job_name, tickers_requested),
                )
                job_id = cur.fetchone()[0]
            conn.commit()
            return job_id

    def finish_job(
        self,
        job_id: int,
        *,
        status: str,
        tickers_fetched: int = 0,
        tickers_failed: int = 0,
        error_message: str | None = None,
    ) -> None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE job_runs
                    SET finished_at = NOW(), status = %s,
                        tickers_fetched = %s, tickers_failed = %s,
                        error_message = %s
                    WHERE id = %s
                    """,
                    (status, tickers_fetched, tickers_failed, error_message, job_id),
                )
            conn.commit()

    def latest_job(self, job_name: str | None = None) -> dict[str, Any] | None:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if job_name:
                    cur.execute(
                        """
                        SELECT id, job_name, started_at, finished_at, status,
                               tickers_requested, tickers_fetched, tickers_failed, error_message
                        FROM job_runs
                        WHERE job_name = %s
                        ORDER BY started_at DESC
                        LIMIT 1
                        """,
                        (job_name,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, job_name, started_at, finished_at, status,
                               tickers_requested, tickers_fetched, tickers_failed, error_message
                        FROM job_runs
                        ORDER BY started_at DESC
                        LIMIT 1
                        """
                    )
                row = cur.fetchone()
                if not row:
                    return None
                keys = [
                    "id",
                    "job_name",
                    "started_at",
                    "finished_at",
                    "status",
                    "tickers_requested",
                    "tickers_fetched",
                    "tickers_failed",
                    "error_message",
                ]
                return dict(zip(keys, row, strict=True))
