from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from quant_hub.application.universe_service import UniverseService
from quant_hub.config import LEGACY_BREAKOUT_OUTPUTS, scan_output_paths
from quant_hub.engine.export import ticker_results_to_legacy_scores
from quant_hub.engine.runner import StrategyEngine
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository
from quant_hub.notify.email import send_scan_email
from quant_hub.report.builder import build_scan_report
from quant_hub.report.export import copy_to_legacy, export_json_report, export_markdown_report
from quant_hub.scoring.aggregate import export_results
from quant_hub.strategies.registry import get_strategy

logger = logging.getLogger(__name__)


class ScanService:
    def __init__(
        self,
        *,
        strategy_id: str = "breakout",
        universe_service: UniverseService | None = None,
        scan_repo: ScanRepository | None = None,
        job_repo: JobRunRepository | None = None,
    ) -> None:
        self.strategy_id = strategy_id
        self.universe_service = universe_service or UniverseService()
        self.scan_repo = scan_repo or ScanRepository()
        self.job_repo = job_repo or JobRunRepository()

    def run(
        self,
        *,
        universe_id: str | None = None,
        tickers: list[str] | None = None,
        tickers_file: Path | None = None,
        use_cache: bool = False,
        dry_run: bool = False,
        output: Path | None = None,
        report: str | None = "json",
        report_json: Path | None = None,
        report_md: Path | None = None,
        send_email: bool = False,
        scan_date: date | None = None,
        job_name: str | None = None,
        persist: bool = True,
    ) -> pd.DataFrame:
        scan_date = scan_date or date.today()
        resolved_id, universe = self.universe_service.resolve(
            universe_id=universe_id,
            tickers=tickers,
            tickers_file=tickers_file,
        )

        paths = scan_output_paths(self.strategy_id, resolved_id)
        output = output or paths["csv"]
        report_json = report_json or paths["json"]
        report_md = report_md or paths["md"]

        job_id = None
        if job_name:
            job_id = self.job_repo.start_job(job_name, tickers_requested=len(universe))

        try:
            spec = get_strategy(self.strategy_id)
            engine = StrategyEngine(
                spec,
                tickers=universe,
                use_cache=use_cache,
                dry_run=dry_run,
            )
            scan_result = engine.run()
            results = scan_result.to_dataframe()
            export_results(results, output)
            logger.info("Wrote %d rows to %s", len(results), output)

            ctx = engine._context
            assert ctx is not None
            scores_by_ticker = ticker_results_to_legacy_scores(scan_result.tickers)
            scan_report = build_scan_report(
                results_df=results,
                universe=scan_result.universe,
                stock_dfs=ctx.stock_dfs,
                spy_df=ctx.spy_df,
                sector_dfs=ctx.sector_dfs,
                sector_etfs=ctx.sector_etfs,
                fund_map=ctx.fund_map,
                regime_detail=scan_result.regime_detail,
                scores_by_ticker=scores_by_ticker,
                strategy_id=scan_result.strategy_id,
                fundamentals_quality=ctx.extras.get("fundamentals_quality"),
            )

            if report in ("json", "both"):
                export_json_report(scan_report, report_json)
                logger.info("Wrote JSON report to %s", report_json)
            if report in ("md", "both"):
                export_markdown_report(scan_report, report_md)
                logger.info("Wrote markdown report to %s", report_md)

            if self.strategy_id == "breakout" and resolved_id == "sp500":
                copy_to_legacy(output, LEGACY_BREAKOUT_OUTPUTS["csv"])
                if report in ("json", "both"):
                    copy_to_legacy(report_json, LEGACY_BREAKOUT_OUTPUTS["json"])
                if report in ("md", "both"):
                    copy_to_legacy(report_md, LEGACY_BREAKOUT_OUTPUTS["md"])

            if persist:
                run_id = self.scan_repo.upsert_scan(
                    scan_date=scan_date,
                    strategy_id=self.strategy_id,
                    universe_id=resolved_id,
                    report=scan_report,
                )
                logger.info("Persisted scan to Postgres run_id=%s", run_id)

            if send_email:
                    if send_scan_email(scan_report, scan_date=scan_date):
                        logger.info("Actionable tickers email sent")
                    else:
                        logger.warning(
                            "Email not sent — configure SMTP_HOST, SMTP_USER, SMTP_PASSWORD, EMAIL_TO"
                        )

            if job_id is not None:
                fetched = len([t for t in scan_result.tickers if t.eligible or t.filter_reason != "no_price_data"])
                failed = len(universe) - len(scan_result.universe)
                self.job_repo.finish_job(
                    job_id,
                    status="success",
                    tickers_fetched=fetched,
                    tickers_failed=max(failed, 0),
                )

            return results

        except Exception as exc:
            if job_id is not None:
                self.job_repo.finish_job(
                    job_id,
                    status="failed",
                    error_message=str(exc),
                )
            raise
