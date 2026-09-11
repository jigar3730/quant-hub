"""Export flattened ML feature matrices to Parquet, with a quality gate for
data meant to leave this repo (ML training, LLM/RAG corpora, external tools).

Mirrors the guardrails already enforced in ml/training_set.py so the two
export paths cannot silently drift apart: same label_status/tier filtering,
same signal embargo. Every export also writes a JSON manifest recording row
counts, drop reasons, and provenance so a downstream consumer (or an LLM
fine-tune/RAG pipeline) can tell what quality bar the data cleared without
re-deriving it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from quant_hub.config import DEFAULT_LABEL_HORIZONS, ML_FEATURES_DIR
from quant_hub.infrastructure.postgres.outcomes_repository import OutcomesRepository
from quant_hub.infrastructure.postgres.repository import ScanRepository
from quant_hub.ml.constants import (
    FEATURE_SCHEMA_VERSION,
    LABEL_STATUS_OK,
    LAUNCHPAD_SETUP_TIERS,
)
from quant_hub.ml.features import extract_features, merge_outcome_columns
from quant_hub.ml.walk_forward import apply_ticker_signal_embargo

logger = logging.getLogger(__name__)


@dataclass
class ExportStats:
    runs_processed: int = 0
    rows_raw: int = 0
    rows_written: int = 0
    drop_tier: int = 0
    drop_label_status: int = 0
    drop_fetch_incomplete: int = 0
    drop_embargo: int = 0
    output_paths: list[Path] = field(default_factory=list)

    def summary(self) -> str:
        paths = ", ".join(str(p) for p in self.output_paths) or "(none)"
        return (
            f"runs={self.runs_processed} raw={self.rows_raw} written={self.rows_written} "
            f"drops[tier={self.drop_tier} label={self.drop_label_status} "
            f"fetch={self.drop_fetch_incomplete} embargo={self.drop_embargo}] "
            f"paths=[{paths}]"
        )

    def drop_reasons(self) -> dict[str, int]:
        return {
            "tier": self.drop_tier,
            "label_status": self.drop_label_status,
            "fetch_incomplete": self.drop_fetch_incomplete,
            "embargo": self.drop_embargo,
        }


class MLExportService:
    def __init__(
        self,
        *,
        scan_repo: ScanRepository | None = None,
        outcomes_repo: OutcomesRepository | None = None,
        output_dir: Path | None = None,
    ) -> None:
        self.scan_repo = scan_repo or ScanRepository()
        self.outcomes_repo = outcomes_repo or OutcomesRepository()
        self.output_dir = output_dir or ML_FEATURES_DIR

    def run(
        self,
        *,
        run_id: int | None = None,
        strategy_id: str | None = None,
        universe_id: str | None = None,
        since: date | None = None,
        until: date | None = None,
        horizon_days: int | None = None,
        include_labels: bool = True,
        per_run_files: bool = False,
        quality_gate: bool = True,
        setups_only: bool = True,
    ) -> ExportStats:
        """Export flattened, labeled feature rows to Parquet.

        quality_gate=True (default) drops rows that would corrupt a training
        set or a downstream LLM/RAG corpus: non-setup tiers, non-`ok` label
        status, and incomplete-fetch rows, then applies the same per-ticker
        signal embargo used for model training. Every quality column
        (fetch_complete/fetch_error/label_status) is kept in the output
        regardless of the gate so a consumer can audit or re-filter.
        Pass quality_gate=False for an unfiltered dump (e.g. auditing the
        raw feed itself) — never use that output for training without
        filtering it downstream.
        """
        stats = ExportStats()
        if run_id is not None:
            run = self.scan_repo.get_run_by_id(run_id)
            runs = [run] if run else []
        else:
            runs = self.scan_repo.list_runs_filtered(
                strategy_id=strategy_id,
                universe_id=universe_id,
                since=since,
                until=until,
            )

        if not runs:
            logger.warning("No scan runs matched export filters")
            return stats

        if horizon_days is None and include_labels:
            horizon_days = DEFAULT_LABEL_HORIZONS[1]  # default 10d

        all_rows: list[dict] = []
        for run in runs:
            stats.runs_processed += 1
            strategy = run["strategy_id"]
            outcome_map: dict[str, dict] = {}
            if include_labels and horizon_days is not None:
                outcome_map = self.outcomes_repo.outcome_map_for_run(
                    run["id"], horizon_days=horizon_days
                )

            details = self.scan_repo.list_ticker_details_for_run(run["id"])
            run_rows: list[dict] = []
            run_stats = ExportStats()  # per-run counters, for per-run manifests
            for detail in details:
                stats.rows_raw += 1
                run_stats.rows_raw += 1
                features = extract_features(
                    strategy_id=strategy,
                    detail=detail,
                    run=run,
                )

                if quality_gate and strategy == "launchpad" and setups_only:
                    tier = detail.get("tier") or ""
                    if tier not in LAUNCHPAD_SETUP_TIERS:
                        stats.drop_tier += 1
                        run_stats.drop_tier += 1
                        continue

                if quality_gate and strategy == "lynch" and features.get("fetch_error"):
                    stats.drop_fetch_incomplete += 1
                    run_stats.drop_fetch_incomplete += 1
                    continue

                outcome = None
                ticker = detail.get("ticker")
                if include_labels and horizon_days is not None:
                    outcome = outcome_map.get(ticker) if ticker else None
                    # signal_outcomes only exists for launchpad; lynch has no
                    # forward-return labels, so it never gates on label_status.
                    if quality_gate and strategy == "launchpad":
                        status = outcome.get("label_status") if outcome else None
                        if status != LABEL_STATUS_OK:
                            stats.drop_label_status += 1
                            run_stats.drop_label_status += 1
                            continue

                row = merge_outcome_columns(features, outcome)
                run_rows.append(row)

            if quality_gate and include_labels and strategy == "launchpad" and run_rows:
                before = len(run_rows)
                run_rows = apply_ticker_signal_embargo(pd.DataFrame(run_rows)).to_dict("records")
                dropped = before - len(run_rows)
                stats.drop_embargo += dropped
                run_stats.drop_embargo += dropped

            all_rows.extend(run_rows)

            if per_run_files and run_rows:
                path = self._write_parquet(
                    run_rows,
                    strategy_id=strategy,
                    universe_id=run["universe_id"],
                    scan_date=run["scan_date"],
                    run_id=run["id"],
                    horizon_days=horizon_days,
                )
                stats.output_paths.append(path)
                stats.rows_written += len(run_rows)
                self._write_manifest(
                    path,
                    stats=run_stats,
                    strategy_id=strategy,
                    universe_id=run["universe_id"],
                    since=run["scan_date"],
                    until=run["scan_date"],
                    horizon_days=horizon_days,
                    quality_gate=quality_gate,
                    row_count=len(run_rows),
                )

        if not per_run_files and all_rows:
            path = self._write_parquet(
                all_rows,
                strategy_id=strategy_id or "all",
                universe_id=universe_id or "all",
                scan_date=since or runs[-1]["scan_date"],
                run_id=None,
                horizon_days=horizon_days,
            )
            stats.output_paths.append(path)
            stats.rows_written = len(all_rows)
            self._write_manifest(
                path,
                stats=stats,
                strategy_id=strategy_id or "all",
                universe_id=universe_id or "all",
                since=since,
                until=until,
                horizon_days=horizon_days,
                quality_gate=quality_gate,
                row_count=len(all_rows),
            )

        logger.info("ML feature export complete: %s", stats.summary())
        return stats

    def _write_parquet(
        self,
        rows: list[dict],
        *,
        strategy_id: str,
        universe_id: str,
        scan_date: date,
        run_id: int | None,
        horizon_days: int | None = None,
    ) -> Path:
        df = pd.DataFrame(rows)
        base = self.output_dir / strategy_id / universe_id
        base.mkdir(parents=True, exist_ok=True)
        if run_id is not None:
            suffix = f"run_{run_id}"
        else:
            suffix = f"{scan_date}_export"
        if horizon_days is not None:
            suffix = f"{suffix}_h{horizon_days}"
        path = base / f"features_{suffix}.parquet"
        df.to_parquet(path, index=False)
        return path

    def _write_manifest(
        self,
        parquet_path: Path,
        *,
        stats: ExportStats,
        strategy_id: str,
        universe_id: str,
        since: date | None,
        until: date | None,
        horizon_days: int | None,
        quality_gate: bool,
        row_count: int,
    ) -> Path:
        """Write a dataset-card-style manifest next to the Parquet file.

        This is the provenance record a downstream ML/LLM training job
        should check before trusting the data: what quality bar it cleared,
        how many rows were dropped and why, and what schema version it is.
        """
        manifest = {
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "quant_hub.MLExportService",
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "strategy_id": strategy_id,
            "universe_id": universe_id,
            "since": str(since) if since else None,
            "until": str(until) if until else None,
            "horizon_days": horizon_days,
            "quality_gate": quality_gate,
            "row_counts": {
                "raw": stats.rows_raw,
                "written": row_count,
                "dropped": stats.drop_reasons(),
            },
            "warning": None
            if quality_gate
            else (
                "quality_gate=False: this export includes non-setup tiers, "
                "non-'ok' label rows, and incomplete-fetch rows. Do not use "
                "for model/LLM training without filtering downstream."
            ),
        }
        manifest_path = parquet_path.with_suffix(".manifest.json")
        manifest_path.write_text(json.dumps(manifest, indent=2))
        return manifest_path
