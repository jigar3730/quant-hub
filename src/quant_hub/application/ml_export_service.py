"""Export flattened ML feature matrices to Parquet."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from quant_hub.config import DEFAULT_LABEL_HORIZONS, ML_FEATURES_DIR
from quant_hub.infrastructure.postgres.outcomes_repository import OutcomesRepository
from quant_hub.infrastructure.postgres.repository import ScanRepository
from quant_hub.ml.features import extract_features, merge_outcome_columns

logger = logging.getLogger(__name__)


@dataclass
class ExportStats:
    runs_processed: int = 0
    rows_written: int = 0
    output_paths: list[Path] = field(default_factory=list)

    def summary(self) -> str:
        paths = ", ".join(str(p) for p in self.output_paths) or "(none)"
        return f"runs={self.runs_processed} rows={self.rows_written} paths=[{paths}]"


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
    ) -> ExportStats:
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
            for detail in details:
                features = extract_features(
                    strategy_id=strategy,
                    detail=detail,
                    run=run,
                )
                ticker = detail.get("ticker")
                outcome = outcome_map.get(ticker) if ticker else None
                row = merge_outcome_columns(features, outcome)
                run_rows.append(row)
                all_rows.append(row)

            if per_run_files and run_rows:
                path = self._write_parquet(
                    run_rows,
                    strategy_id=strategy,
                    universe_id=run["universe_id"],
                    scan_date=run["scan_date"],
                    run_id=run["id"],
                )
                stats.output_paths.append(path)
                stats.rows_written += len(run_rows)

        if not per_run_files and all_rows:
            path = self._write_parquet(
                all_rows,
                strategy_id=strategy_id or "all",
                universe_id=universe_id or "all",
                scan_date=since or runs[-1]["scan_date"],
                run_id=None,
            )
            stats.output_paths.append(path)
            stats.rows_written = len(all_rows)

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
    ) -> Path:
        df = pd.DataFrame(rows)
        base = self.output_dir / strategy_id / universe_id
        base.mkdir(parents=True, exist_ok=True)
        suffix = f"run_{run_id}" if run_id is not None else f"{scan_date}_export"
        path = base / f"features_{suffix}.parquet"
        df.to_parquet(path, index=False)
        return path
