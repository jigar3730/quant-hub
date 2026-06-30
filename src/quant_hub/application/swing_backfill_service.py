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
from quant_hub.ml.backfill_dates import (
    as_scan_date,
    compute_backfill_coverage,
    earliest_backfill_supported,
    iter_weekly_scan_dates,
    truncate_weekly_to_date,
)

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
    dates_missing_before: int = 0
    earliest_written: date | None = None
    latest_written: date | None = None
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [
            f"planned={self.dates_planned}",
            f"written={self.dates_written}",
            f"skipped={self.dates_skipped}",
            f"failed={self.dates_failed}",
            f"setups={self.total_setups}",
        ]
        if self.dates_missing_before:
            parts.append(f"missing_before_run={self.dates_missing_before}")
        if self.earliest_written:
            parts.append(f"written_range={self.earliest_written}..{self.latest_written}")
        return " ".join(parts)


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

        existing_dates: list[date] = []
        if resume:
            for run in self.scan_repo.list_runs_filtered(
                strategy_id="swing",
                universe_id=resolved_id,
                since=since,
                until=until,
            ):
                normalized = as_scan_date(run["scan_date"])
                if normalized is not None:
                    existing_dates.append(normalized)

        coverage = compute_backfill_coverage(
            since=since,
            until=until,
            existing_dates=existing_dates,
        )
        stats.dates_missing_before = len(coverage.missing_dates)
        existing = coverage.existing_dates if resume else set()

        supported_since = earliest_backfill_supported(min_weekly_bars=SWING_MIN_BARS)
        if scan_dates[0] < supported_since:
            logger.warning(
                "Earliest requested Friday %s is before reliable 10y weekly cache support (~%s). "
                "Early dates may fail or produce sparse indicators.",
                scan_dates[0],
                supported_since,
            )

        logger.info(
            "Swing backfill %s: %s resume=%s dry_run=%s",
            resolved_id,
            coverage.summary(),
            resume,
            dry_run,
        )
        for line in coverage.detail_lines():
            logger.info("  %s", line)

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
            to_write = sum(1 for d in scan_dates if not (resume and d in existing))
            logger.info("Processing %d Fridays (%d to write, %d to skip)", len(scan_dates), to_write, len(scan_dates) - to_write)

            for idx, scan_date in enumerate(scan_dates, start=1):
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
                    if stats.earliest_written is None or scan_date < stats.earliest_written:
                        stats.earliest_written = scan_date
                    if stats.latest_written is None or scan_date > stats.latest_written:
                        stats.latest_written = scan_date
                    if idx % 25 == 0 or idx == len(scan_dates):
                        logger.info(
                            "Backfill progress %d/%d written=%d failed=%d last=%s",
                            idx,
                            len(scan_dates),
                            stats.dates_written,
                            stats.dates_failed,
                            scan_date,
                        )
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

    def coverage(
        self,
        *,
        universe_id: str = "sp500",
        since: date,
        until: date | None = None,
    ):
        """Report planned vs existing Friday scan dates without running scans."""
        until = until or date.today()
        resolved_id, _universe = self.universe_service.resolve(universe_id=universe_id)
        existing_dates: list[date] = []
        for run in self.scan_repo.list_runs_filtered(
            strategy_id="swing",
            universe_id=resolved_id,
            since=since,
            until=until,
        ):
            normalized = as_scan_date(run["scan_date"])
            if normalized is not None:
                existing_dates.append(normalized)
        return compute_backfill_coverage(
            since=since,
            until=until,
            existing_dates=existing_dates,
        )
