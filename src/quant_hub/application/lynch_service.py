"""Lynch scan application service — Postgres persist and email."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from quant_hub.application.universe_service import UniverseService
from quant_hub.config import LEGACY_LYNCH_OUTPUTS, scan_output_paths
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository
from quant_hub.lynch.runner import LynchScannerRunner
from quant_hub.notify.email import send_lynch_email
from quant_hub.report.export import copy_to_legacy

logger = logging.getLogger(__name__)


class LynchScanService:
    def __init__(
        self,
        *,
        universe_service: UniverseService | None = None,
        scan_repo: ScanRepository | None = None,
        job_repo: JobRunRepository | None = None,
    ) -> None:
        self.universe_service = universe_service or UniverseService()
        self.scan_repo = scan_repo or ScanRepository()
        self.job_repo = job_repo or JobRunRepository()

    def run(
        self,
        *,
        universe_id: str = "sp500",
        tickers: list[str] | None = None,
        tickers_file: Path | None = None,
        preset: str = "summary",
        output: Path | None = None,
        report: str | None = "both",
        persist: bool = True,
        send_email: bool = True,
        scan_date: date | None = None,
        job_name: str | None = "lynch-weekly",
    ) -> pd.DataFrame:
        scan_date = scan_date or date.today()
        resolved_id, universe = self.universe_service.resolve(
            universe_id=universe_id,
            tickers=tickers,
            tickers_file=tickers_file,
        )

        paths = scan_output_paths("lynch", resolved_id)
        output = output or paths["csv"]

        job_id = None
        if job_name:
            job_id = self.job_repo.start_job(job_name, tickers_requested=len(universe))

        try:
            runner = LynchScannerRunner(
                universe=universe,
                preset=preset,
                output=output,
                report=report,
                report_json=paths["json"],
                report_md=paths["md"],
                universe_id=resolved_id,
            )
            df, scan_report = runner.run()

            if resolved_id == "sp500":
                copy_to_legacy(paths["csv"], LEGACY_LYNCH_OUTPUTS["csv"])
                if report in ("json", "both"):
                    copy_to_legacy(paths["json"], LEGACY_LYNCH_OUTPUTS["json"])
                if report in ("md", "both"):
                    copy_to_legacy(paths["md"], LEGACY_LYNCH_OUTPUTS["md"])

            if persist:
                run_id = self.scan_repo.upsert_scan(
                    scan_date=scan_date,
                    strategy_id="lynch",
                    universe_id=resolved_id,
                    report=scan_report,
                )
                logger.info("Persisted Lynch scan to Postgres run_id=%s", run_id)

            if send_email:
                if send_lynch_email(scan_report, scan_date=scan_date):
                    logger.info("Lynch candidates email sent")
                else:
                    logger.warning(
                        "Email not sent — configure SMTP_HOST, SMTP_USER, SMTP_PASSWORD, EMAIL_TO"
                    )

            if job_id is not None:
                fetched = sum(1 for r in scan_report["tickers"] if not r.get("metrics", {}).get("error"))
                failed = len(universe) - fetched
                self.job_repo.finish_job(
                    job_id,
                    status="success",
                    tickers_fetched=fetched,
                    tickers_failed=max(failed, 0),
                )

            passed = scan_report["scan_summary"]["passed_count"]
            logger.info(
                "Lynch scan complete: %d passed / %d tickers (preset=%s)",
                passed,
                len(universe),
                preset,
            )
            return df

        except Exception:
            if job_id is not None:
                self.job_repo.finish_job(job_id, status="error", error_message="lynch scan failed")
            raise
