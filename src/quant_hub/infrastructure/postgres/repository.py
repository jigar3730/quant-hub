from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any

from quant_hub.infrastructure.postgres.connection import get_connection
from quant_hub.infrastructure.postgres.fixtures import (
    FIXTURE_UNIVERSE_IDS,
    is_fixture_scan_date,
)
from quant_hub.serialization.json_util import json_dumps

logger = logging.getLogger(__name__)

METADATA_SCHEMA_VERSION = 1


def _fixture_sql_clause(exclude_fixtures: bool) -> tuple[str, list[Any]]:
    if not exclude_fixtures:
        return "", []
    fixtures = list(FIXTURE_UNIVERSE_IDS)
    placeholders = ", ".join(["%s"] * len(fixtures))
    return f"scan_date <= CURRENT_DATE AND universe_id NOT IN ({placeholders})", fixtures


def _build_scan_metadata(report: dict) -> dict[str, Any]:
    """Persist full scan context needed to rebuild analyst-facing reports."""
    summary = report["scan_summary"]
    regime = report["market_regime"]
    metadata: dict[str, Any] = {
        "schema_version": METADATA_SCHEMA_VERSION,
        "market_regime": regime,
        "filter_breakdown": summary.get("filter_breakdown", {}),
        "eligible_count": summary.get("eligible_count"),
        "excluded_count": summary.get("excluded_count"),
        "setup_long_count": summary.get("setup_long_count"),
        "setup_short_count": summary.get("setup_short_count"),
        "fundamentals_quality": summary.get("fundamentals_quality"),
    }
    if report.get("strategy_id") == "lynch":
        metadata.update(
            {
                "preset": summary.get("preset"),
                "preset_label": summary.get("preset_label"),
                "passed_count": summary.get("passed_count"),
                "category_counts": summary.get("category_counts"),
                "qualitative_overlay": report.get("qualitative_overlay"),
            }
        )
    return metadata


def _restore_market_regime(run: dict[str, Any]) -> dict[str, Any]:
    metadata = run.get("metadata") or {}
    stored = metadata.get("market_regime")
    if isinstance(stored, dict) and stored:
        return dict(stored)

    # Legacy rows written before full regime persistence.
    return {
        "label": run.get("regime_label", "unknown"),
        "multiplier": run.get("regime_multiplier", 1.0),
        "spy_price": metadata.get("spy_price"),
        "return_63d_pct": metadata.get("return_63d_pct"),
    }


def _tier_counts_from_run(run: dict[str, Any], metadata: dict[str, Any]) -> dict[str, int]:
    strategy_id = run.get("strategy_id", "breakout")
    if strategy_id == "swing":
        return {
            "SETUP_LONG": run.get("tier1_count", 0),
            "SETUP_SHORT": run.get("tier2_count", 0),
            "filtered": run.get("filtered_count", 0),
        }
    if strategy_id == "lynch":
        cats = metadata.get("category_counts") or {}
        return {
            "fast_grower": cats.get("fast_grower", run.get("tier1_count", 0)),
            "stalwart": cats.get("stalwart", run.get("tier2_count", 0)),
            "asset_play": cats.get("asset_play", run.get("tier3_count", 0)),
            "filtered": run.get("filtered_count", 0),
        }
    return {
        "Tier 1": run.get("tier1_count", 0),
        "Tier 2": run.get("tier2_count", 0),
        "Tier 3": run.get("tier3_count", 0),
        "filtered": run.get("filtered_count", 0),
    }


def _tier_counts_from_report(strategy_id: str, tiers: dict[str, int]) -> tuple[int, int, int, int]:
    if strategy_id == "swing":
        return (
            tiers.get("SETUP_LONG", tiers.get("Tier 1", 0)),
            tiers.get("SETUP_SHORT", tiers.get("Tier 2", 0)),
            0,
            tiers.get("filtered", 0),
        )
    if strategy_id == "lynch":
        return (
            tiers.get("fast_grower", 0),
            tiers.get("stalwart", 0),
            tiers.get("asset_play", 0),
            tiers.get("filtered", 0),
        )
    return (
        tiers.get("Tier 1", 0),
        tiers.get("Tier 2", 0),
        tiers.get("Tier 3", 0),
        tiers.get("filtered", 0),
    )


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
        tiers = summary["tier_counts"]
        tier1, tier2, tier3, filtered = _tier_counts_from_report(strategy_id, tiers)
        scan_time = scan_time or datetime.now(timezone.utc)
        metadata = _build_scan_metadata(report)

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
                        tier1,
                        tier2,
                        tier3,
                        filtered,
                        summary.get("actionable_count", 0),
                        report["market_regime"].get("label"),
                        report["market_regime"].get("multiplier"),
                        json_dumps(metadata),
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
                            json_dumps(ticker),
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
        exclude_fixtures: bool = True,
    ) -> dict[str, Any] | None:
        clauses = ["strategy_id = %s"]
        params: list[Any] = [strategy_id]
        if universe_id:
            clauses.append("universe_id = %s")
            params.append(universe_id)
        if scan_date:
            clauses.append("scan_date = %s")
            params.append(scan_date)
        elif exclude_fixtures:
            fixture_clause, fixture_params = _fixture_sql_clause(True)
            clauses.append(fixture_clause)
            params.extend(fixture_params)

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
        exclude_fixtures: bool = True,
    ) -> dict[str, Any] | None:
        run = self.get_latest_run(
            strategy_id=strategy_id,
            universe_id=universe_id,
            scan_date=scan_date,
            exclude_fixtures=exclude_fixtures,
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
        tier_counts = _tier_counts_from_run(run, metadata)
        scan_summary: dict[str, Any] = {
            "universe_size": run.get("universe_size", len(tickers)),
            "eligible_count": metadata.get("eligible_count", 0),
            "excluded_count": metadata.get("excluded_count", 0),
            "tier_counts": tier_counts,
            "actionable_count": run.get("actionable_count", 0),
            "filter_breakdown": metadata.get("filter_breakdown", {}),
            "setup_long_count": metadata.get("setup_long_count"),
            "setup_short_count": metadata.get("setup_short_count"),
            "fundamentals_quality": metadata.get("fundamentals_quality"),
        }
        if run["strategy_id"] == "lynch":
            scan_summary.update(
                {
                    "preset": metadata.get("preset"),
                    "preset_label": metadata.get("preset_label"),
                    "passed_count": metadata.get(
                        "passed_count", run.get("actionable_count", 0)
                    ),
                    "category_counts": metadata.get("category_counts", tier_counts),
                    "scanner": "peter_lynch",
                }
            )

        result: dict[str, Any] = {
            "strategy_id": run["strategy_id"],
            "universe_id": run["universe_id"],
            "scan_date": str(run["scan_date"]),
            "scan_time": run["scan_time"].isoformat() if run["scan_time"] else None,
            "scan_summary": scan_summary,
            "market_regime": _restore_market_regime(run),
            "tickers": tickers,
        }
        if run["strategy_id"] == "lynch":
            passed = [t for t in tickers if t.get("passed")]
            result["candidates"] = sorted(
                passed,
                key=lambda t: (t.get("lynch_score", 0), -(t.get("peg_ratio") or 99)),
                reverse=True,
            )
            from quant_hub.lynch.categories import QUALITATIVE_OVERLAY

            result["qualitative_overlay"] = metadata.get(
                "qualitative_overlay", QUALITATIVE_OVERLAY
            )
        return result

    def list_runs(
        self,
        *,
        strategy_id: str = "breakout",
        limit: int = 30,
        exclude_fixtures: bool = True,
    ) -> list[dict[str, Any]]:
        clauses = ["strategy_id = %s"]
        params: list[Any] = [strategy_id]
        if exclude_fixtures:
            fixture_clause, fixture_params = _fixture_sql_clause(True)
            clauses.append(fixture_clause)
            params.extend(fixture_params)
        params.append(limit)

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
                    LIMIT %s
                    """,
                    params,
                )
                return [self._row_to_run_dict(row) for row in cur.fetchall()]

    def delete_fixture_runs(self) -> int:
        """Remove test fixture scan runs from production database."""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM scan_runs
                    WHERE universe_id = ANY(%s)
                       OR scan_date > CURRENT_DATE
                    RETURNING id
                    """,
                    (list(FIXTURE_UNIVERSE_IDS),),
                )
                deleted = len(cur.fetchall())
            conn.commit()
            if deleted:
                logger.info("Deleted %d fixture scan run(s)", deleted)
            return deleted

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

    def recent_jobs(self, *, limit: int = 10) -> list[dict[str, Any]]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, job_name, started_at, finished_at, status,
                           tickers_requested, tickers_fetched, tickers_failed, error_message
                    FROM job_runs
                    ORDER BY started_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
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
                return [dict(zip(keys, row, strict=True)) for row in cur.fetchall()]
