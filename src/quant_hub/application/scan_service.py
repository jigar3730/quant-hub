from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from quant_hub.application.run_result import ServiceRunResult
from quant_hub.application.universe_service import UniverseService
from quant_hub.config import scan_output_paths
from quant_hub.data.provenance import build_data_provenance
from quant_hub.data.quality import max_bar_date
from quant_hub.engine.export import ticker_results_to_legacy_scores
from quant_hub.engine.runner import StrategyEngine
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository
from quant_hub.notify.email import send_scan_email
from quant_hub.report.builder import build_scan_report
from quant_hub.report.export import export_json_report, export_markdown_report
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
    ) -> ServiceRunResult:
        scan_date = scan_date or date.today()
        resolved_id, universe = self.universe_service.resolve(
            universe_id=universe_id,
            tickers=tickers,
            tickers_file=tickers_file,
        )

        paths = scan_output_paths(self.strategy_id, resolved_id, dry_run=dry_run)
        output = output or paths["csv"]
        report_json = report_json or paths["json"]
        report_md = report_md or paths["md"]

        job_id = None
        if job_name:
            job_id = self.job_repo.start_job(job_name, tickers_requested=len(universe))

        try:
            spec = get_strategy(self.strategy_id)
            eligibility_mode = self.universe_service.registry.get_eligibility_mode(resolved_id)
            engine = StrategyEngine(
                spec,
                tickers=universe,
                use_cache=use_cache,
                dry_run=dry_run,
                eligibility_mode=eligibility_mode,
            )
            scan_result = engine.run()
            results = scan_result.to_dataframe()
            export_results(results, output)
            logger.info("Wrote %d rows to %s", len(results), output)

            ctx = engine._context
            assert ctx is not None
            scores_by_ticker = ticker_results_to_legacy_scores(scan_result.tickers)
            cache_mode = "parquet" if use_cache else "live"
            as_of = max_bar_date(ctx.spy_df)
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
                eligibility_mode=eligibility_mode,
                data_provenance=build_data_provenance(
                    strategy_id=scan_result.strategy_id,
                    universe_id=resolved_id,
                    scan_date=scan_date,
                    price_cache=cache_mode,
                    fundamentals_cache=cache_mode,
                    as_of_price=str(as_of) if as_of else None,
                    extra={"dry_run": True} if dry_run else None,
                ),
            )

            if report in ("json", "both"):
                export_json_report(scan_report, report_json)
                logger.info("Wrote JSON report to %s", report_json)
            if report in ("md", "both"):
                export_markdown_report(scan_report, report_md)
                logger.info("Wrote markdown report to %s", report_md)

            if persist:
                run_id = self.scan_repo.upsert_scan(
                    scan_date=scan_date,
                    strategy_id=self.strategy_id,
                    universe_id=resolved_id,
                    report=scan_report,
                )
                logger.info("Persisted scan to Postgres run_id=%s", run_id)

            email_sent = False
            if send_email:
                email_sent = send_scan_email(scan_report, scan_date=scan_date)
                if email_sent:
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

            return ServiceRunResult(
                dataframe=results,
                email_requested=send_email,
                email_sent=email_sent if send_email else False,
            )

        except Exception as exc:
            if job_id is not None:
                self.job_repo.finish_job(
                    job_id,
                    status="failed",
                    error_message=str(exc),
                )
            raise
