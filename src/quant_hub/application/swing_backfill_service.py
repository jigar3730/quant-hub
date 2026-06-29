"""Historical point-in-time swing scans for ML training data."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from quant_hub.application.swing_scan_core import scan_universe_weekly
from quant_hub.application.swing_service import build_swing_report
from quant_hub.application.universe_service import UniverseService
from quant_hub.config import BENCHMARK_TICKER, SWING_MIN_BARS
from quant_hub.data.provenance import build_data_provenance
from quant_hub.data.quality import max_bar_date
from quant_hub.infrastructure.market.weekly_prices import download_weekly_prices
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository
from quant_hub.ml.backfill_dates import iter_weekly_scan_dates, truncate_weekly_to_date

logger = logging.getLogger(__name__)

BACKFILL_VERSION = "v1"
ET = ZoneInfo("America/New_York")


@dataclass
class SwingBackfillStats:
    dates_planned: int = 0
    dates_skipped: int = 0
    dates_written: int = 0
    dates_failed: int = 0
    total_setups: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"planned={self.dates_planned} written={self.dates_written} "
            f"skipped={self.dates_skipped} failed={self.dates_failed} "
            f"setups={self.total_setups}"
        )


class SwingBackfillService:
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
        since: date,
        until: date | None = None,
        resume: bool = True,
        persist: bool = True,
        dry_run: bool = False,
        job_name: str | None = "swing-backfill",
    ) -> SwingBackfillStats:
        until = until or date.today()
        resolved_id, universe = self.universe_service.resolve(universe_id=universe_id)
        scan_dates = iter_weekly_scan_dates(since, until)
        stats = SwingBackfillStats(dates_planned=len(scan_dates))

        if not scan_dates:
            logger.warning("No Friday scan dates in range %s .. %s", since, until)
            return stats

        existing: set[date] = set()
        if resume and persist and not dry_run:
            for run in self.scan_repo.list_runs_filtered(
                strategy_id="swing",
                universe_id=resolved_id,
                since=since,
                until=until,
            ):
                existing.add(run["scan_date"])

        logger.info(
            "Swing backfill %s: %d Fridays (%s .. %s), resume=%s",
            resolved_id,
            len(scan_dates),
            scan_dates[0],
            scan_dates[-1],
            resume,
        )

        price_map_full = download_weekly_prices(
            sorted(set(universe) | {BENCHMARK_TICKER}),
            use_cache=True,
            force_refresh=False,
        )
        if not price_map_full:
            raise RuntimeError("No weekly price data available for backfill")

        job_id = None
        if job_name and persist and not dry_run:
            job_id = self.job_repo.start_job(job_name, tickers_requested=len(universe))

        try:
            for scan_date in scan_dates:
                if resume and scan_date in existing:
                    stats.dates_skipped += 1
                    continue

                try:
                    setups_count = self._backfill_one_date(
                        scan_date=scan_date,
                        universe=universe,
                        resolved_id=resolved_id,
                        price_map_full=price_map_full,
                        persist=persist and not dry_run,
                    )
                    stats.dates_written += 1
                    stats.total_setups += setups_count
                except Exception as exc:
                    stats.dates_failed += 1
                    msg = f"{scan_date}: {exc}"
                    stats.errors.append(msg)
                    logger.exception("Backfill failed for %s", scan_date)

            if job_id is not None:
                status = "success" if stats.dates_failed == 0 else "failed"
                self.job_repo.finish_job(
                    job_id,
                    status=status,
                    tickers_fetched=len(price_map_full),
                    tickers_failed=0,
                    error_message="; ".join(stats.errors[:3]) if stats.errors else None,
                )

            logger.info("Swing backfill complete: %s", stats.summary())
            return stats

        except Exception:
            if job_id is not None:
                self.job_repo.finish_job(job_id, status="failed", error_message="backfill aborted")
            raise

    def _backfill_one_date(
        self,
        *,
        scan_date: date,
        universe: list[str],
        resolved_id: str,
        price_map_full: dict,
        persist: bool,
    ) -> int:
        price_map: dict = {}
        for ticker, df in price_map_full.items():
            price_map[ticker] = truncate_weekly_to_date(df, scan_date)

        spy_df = price_map.get(BENCHMARK_TICKER)
        setups, ticker_reports, rejection_counts = scan_universe_weekly(
            universe,
            price_map,
            spy_df,
            min_bars=SWING_MIN_BARS,
            skip_staleness=True,
        )

        as_of = max_bar_date(spy_df) if spy_df is not None else scan_date
        scan_time = datetime.combine(scan_date, time(17, 45), tzinfo=ET)

        report = build_swing_report(
            universe=universe,
            tickers_report=ticker_reports,
            setups=setups,
            rejection_counts=rejection_counts,
            data_provenance=build_data_provenance(
                strategy_id="swing",
                universe_id=resolved_id,
                scan_date=scan_date,
                price_cache="parquet",
                as_of_price=str(as_of) if as_of else str(scan_date),
                extra={
                    "interval": "1wk",
                    "period": "10y",
                    "backfill": True,
                    "backfill_version": BACKFILL_VERSION,
                },
            ),
        )
        # Override synthetic scan time for historical ordering
        report["data_provenance"]["scan_time_utc"] = scan_time.astimezone(
            ZoneInfo("UTC")
        ).isoformat()

        if persist:
            run_id = self.scan_repo.upsert_scan(
                scan_date=scan_date,
                strategy_id="swing",
                universe_id=resolved_id,
                report=report,
                scan_time=scan_time.astimezone(ZoneInfo("UTC")),
            )
            logger.info(
                "Backfill persisted %s swing/%s run_id=%s setups=%d",
                scan_date,
                resolved_id,
                run_id,
                len(setups),
            )
        else:
            logger.info(
                "Backfill dry-run %s swing/%s setups=%d",
                scan_date,
                resolved_id,
                len(setups),
            )

        return len(setups)
