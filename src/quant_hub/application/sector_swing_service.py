"""Sector-ETF swing scan application service — Postgres persist, exports, job audit."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

from quant_hub.application.run_result import ServiceRunResult
from quant_hub.application.universe_service import UniverseService
from quant_hub.config import scan_output_paths
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository
from quant_hub.infrastructure.postgres.sector_swing_positions_repository import (
    SectorSwingPositionsRepository,
)
from quant_hub.report.export import export_json_report
from quant_hub.sector_swing import config as C
from quant_hub.sector_swing.positions import Position, week_start
from quant_hub.sector_swing.report import write_markdown
from quant_hub.sector_swing.runner import SectorSwingRunner

logger = logging.getLogger(__name__)


class SectorSwingScanService:
    def __init__(
        self,
        *,
        universe_service: UniverseService | None = None,
        scan_repo: ScanRepository | None = None,
        job_repo: JobRunRepository | None = None,
        runner_factory: Callable[..., SectorSwingRunner] = SectorSwingRunner,
        positions_repo: SectorSwingPositionsRepository | None = None,
    ) -> None:
        self.universe_service = universe_service or UniverseService()
        self.scan_repo = scan_repo or ScanRepository()
        self.job_repo = job_repo or JobRunRepository()
        self.runner_factory = runner_factory
        self.positions_repo = positions_repo or SectorSwingPositionsRepository()

    def run(
        self,
        *,
        universe_id: str = C.UNIVERSE_ID,
        use_cache: bool = True,
        dry_run: bool = False,
        allow_stale: bool = False,
        equity: float | None = None,
        risk_pct: float | None = None,
        report: str | None = "both",
        persist: bool = True,
        scan_date: date | None = None,
        job_name: str | None = C.JOB_NAME,
    ) -> ServiceRunResult:
        scan_date = scan_date or date.today()
        resolved_id, universe = self.universe_service.resolve(universe_id=universe_id)
        paths = scan_output_paths(C.STRATEGY_ID, resolved_id, dry_run=dry_run)

        job_id = None
        if job_name and not dry_run:
            job_id = self.job_repo.start_job(job_name, tickers_requested=len(universe))

        try:
            # Dry runs use synthetic prices, so open positions are neither gated on nor refreshed.
            positions: list[Position] = []
            week_pnl = 0.0
            if not dry_run:
                positions = [
                    Position.from_row(row)
                    for row in self.positions_repo.list_positions(status="open")
                ]
                week_pnl = self.positions_repo.realized_pnl_between(week_start(scan_date), scan_date)

            runner = self.runner_factory(
                universe=universe,
                universe_id=resolved_id,
                equity=equity,
                risk_pct=risk_pct,
                use_cache=use_cache,
                dry_run=dry_run,
                allow_stale=allow_stale,
                scan_date=scan_date,
                positions=positions,
                week_realized_pnl=week_pnl,
            )
            df, scan_report = runner.run()

            paths["csv"].parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(paths["csv"], index=False)
            if report in ("json", "both"):
                export_json_report(scan_report, paths["json"])
            if report in ("md", "both"):
                write_markdown(scan_report, paths["md"])

            if persist and not dry_run:
                run_id = self.scan_repo.upsert_scan(
                    scan_date=scan_date,
                    strategy_id=C.STRATEGY_ID,
                    universe_id=resolved_id,
                    report=scan_report,
                )
                logger.info("Persisted sector swing scan to Postgres run_id=%s", run_id)
                self._write_position_updates(runner)

            if job_id is not None:
                summary = scan_report["scan_summary"]
                self.job_repo.finish_job(
                    job_id,
                    status="success",
                    tickers_fetched=summary["tickers_fetched"],
                    tickers_failed=summary["tickers_failed"],
                )
            return ServiceRunResult(dataframe=df)

        except Exception as exc:
            if job_id is not None:
                self.job_repo.finish_job(job_id, status="failed", error_message=str(exc))
            raise

    def _write_position_updates(self, runner: SectorSwingRunner) -> None:
        for pos, status in runner.position_updates:
            if status is None or pos.id is None:
                continue
            self.positions_repo.update_tracking(pos.id, status.to_row())
            if status.exit_signal:
                logger.warning(
                    "Exit signal for %s (position %s): %s on %s — %s",
                    pos.ticker, pos.id, status.exit_signal, status.exit_signal_date,
                    status.exit_signal_detail,
                )
