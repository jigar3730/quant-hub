"""Historical point-in-time Launchpad scans (Saturday launchpad-all cadence)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

from quant_hub.application.universe_service import UniverseService
from quant_hub.config import (
    ALL_SECTOR_ETFS,
    BENCHMARK_TICKER,
    LAUNCHPAD_MIN_HISTORY_DAYS,
    ML_LABEL_CACHE_SUBDIR,
    ML_LABEL_CACHE_TTL_HOURS,
    ML_LABEL_LOOKBACK_DAYS,
)
from quant_hub.data.provenance import build_data_provenance
from quant_hub.data.quality import max_bar_date
from quant_hub.engine.context import ScanContext
from quant_hub.engine.export import ticker_results_to_legacy_scores
from quant_hub.engine.runner import StrategyEngine
from quant_hub.infrastructure.cache.parquet_cache import ParquetCache
from quant_hub.infrastructure.market.yfinance_prices import download_prices
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository
from quant_hub.ml.backfill_dates import (
    BackfillCoverage,
    as_scan_date,
    compute_backfill_coverage,
    earliest_daily_backfill_supported,
    iter_saturday_scan_dates,
    truncate_daily_to_date,
)
from quant_hub.report.builder import build_scan_report
from quant_hub.strategies.registry import get_strategy
from quant_hub.universes.batch import list_universe_ids

logger = logging.getLogger(__name__)

BACKFILL_VERSION = "v1"
ET = ZoneInfo("America/New_York")
LAUNCHPAD_BATCH_TIME = time(1, 30)


@dataclass
class LaunchpadBackfillStats:
    universes_planned: int = 0
    dates_planned: int = 0
    dates_skipped: int = 0
    dates_written: int = 0
    dates_failed: int = 0
    dates_missing_before: int = 0
    earliest_written: date | None = None
    latest_written: date | None = None
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [
            f"universes={self.universes_planned}",
            f"planned={self.dates_planned}",
            f"written={self.dates_written}",
            f"skipped={self.dates_skipped}",
            f"failed={self.dates_failed}",
        ]
        if self.dates_missing_before:
            parts.append(f"missing_before_run={self.dates_missing_before}")
        if self.earliest_written:
            parts.append(f"written_range={self.earliest_written}..{self.latest_written}")
        return " ".join(parts)


class LaunchpadBackfillService:
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
        self._price_cache = ParquetCache(
            base_dir=ML_LABEL_CACHE_SUBDIR,
            ttl_hours=ML_LABEL_CACHE_TTL_HOURS,
        )

    def run_all(
        self,
        *,
        since: date,
        until: date | None = None,
        universe_ids: list[str] | None = None,
        resume: bool = True,
        persist: bool = True,
        dry_run: bool = False,
        job_name: str | None = "launchpad-all-backfill",
    ) -> LaunchpadBackfillStats:
        """Backfill every stock universe used by quant-launchpad-all."""
        ids = universe_ids or list_universe_ids(strategy="launchpad")
        aggregate = LaunchpadBackfillStats(universes_planned=len(ids))
        for universe_id in ids:
            stats = self.run(
                universe_id=universe_id,
                since=since,
                until=until,
                resume=resume,
                persist=persist,
                dry_run=dry_run,
                job_name=None,
            )
            aggregate.dates_planned += stats.dates_planned
            aggregate.dates_skipped += stats.dates_skipped
            aggregate.dates_written += stats.dates_written
            aggregate.dates_failed += stats.dates_failed
            aggregate.dates_missing_before += stats.dates_missing_before
            aggregate.errors.extend(stats.errors)
            if stats.earliest_written and (
                aggregate.earliest_written is None or stats.earliest_written < aggregate.earliest_written
            ):
                aggregate.earliest_written = stats.earliest_written
            if stats.latest_written and (
                aggregate.latest_written is None or stats.latest_written > aggregate.latest_written
            ):
                aggregate.latest_written = stats.latest_written
        if job_name and persist and not dry_run:
            status = "success" if aggregate.dates_failed == 0 else "failed"
            job_id = self.job_repo.start_job(job_name, tickers_requested=len(ids))
            self.job_repo.finish_job(
                job_id,
                status=status,
                tickers_fetched=aggregate.dates_written,
                tickers_failed=aggregate.dates_failed,
                error_message="; ".join(aggregate.errors[:3]) if aggregate.errors else None,
            )
        logger.info("Launchpad-all backfill complete: %s", aggregate.summary())
        return aggregate

    def run(
        self,
        *,
        universe_id: str,
        since: date,
        until: date | None = None,
        resume: bool = True,
        persist: bool = True,
        dry_run: bool = False,
        job_name: str | None = "launchpad-backfill",
    ) -> LaunchpadBackfillStats:
        until = until or date.today()
        resolved_id, universe = self.universe_service.resolve(universe_id=universe_id)
        if self.universe_service.registry.get_eligibility_mode(resolved_id) == "etf":
            logger.warning("Skipping ETF-mode universe %s for launchpad backfill", resolved_id)
            return LaunchpadBackfillStats()

        scan_dates = iter_saturday_scan_dates(since, until)
        stats = LaunchpadBackfillStats(dates_planned=len(scan_dates))
        if not scan_dates:
            logger.warning("No Saturday scan dates in range %s .. %s", since, until)
            return stats

        existing_dates: list[date] = []
        if resume:
            for run in self.scan_repo.list_runs_filtered(
                strategy_id="launchpad",
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
        coverage.planned_dates = scan_dates
        stats.dates_missing_before = len(
            [d for d in scan_dates if d not in coverage.existing_dates]
        )
        existing = coverage.existing_dates if resume else set()

        supported_since = earliest_daily_backfill_supported(
            min_daily_bars=LAUNCHPAD_MIN_HISTORY_DAYS,
            lookback_days=ML_LABEL_LOOKBACK_DAYS,
        )
        if scan_dates[0] < supported_since:
            logger.warning(
                "Earliest requested Saturday %s is before reliable 5y daily cache support (~%s).",
                scan_dates[0],
                supported_since,
            )

        logger.info(
            "Launchpad backfill %s: %s resume=%s dry_run=%s",
            resolved_id,
            _coverage_summary(coverage, scan_dates, existing),
            resume,
            dry_run,
        )

        download_tickers = sorted(set(universe) | set(ALL_SECTOR_ETFS) | {BENCHMARK_TICKER})
        prices_full = download_prices(
            download_tickers,
            use_cache=True,
            lookback_days=ML_LABEL_LOOKBACK_DAYS,
            cache=self._price_cache,
        )
        if prices_full.empty:
            raise RuntimeError("No daily price data available for launchpad backfill")

        eligibility_mode = self.universe_service.registry.get_eligibility_mode(resolved_id)
        spec = get_strategy("launchpad")

        job_id = None
        if job_name and persist and not dry_run:
            job_id = self.job_repo.start_job(job_name, tickers_requested=len(universe))

        try:
            to_write = sum(1 for d in scan_dates if not (resume and d in existing))
            logger.info(
                "Processing %d Saturdays for %s (%d to write, %d to skip)",
                len(scan_dates),
                resolved_id,
                to_write,
                len(scan_dates) - to_write,
            )

            for idx, scan_date in enumerate(scan_dates, start=1):
                if resume and scan_date in existing:
                    stats.dates_skipped += 1
                    continue
                try:
                    self._backfill_one_date(
                        scan_date=scan_date,
                        universe=universe,
                        resolved_id=resolved_id,
                        prices_full=prices_full,
                        spec=spec,
                        eligibility_mode=eligibility_mode,
                        persist=persist and not dry_run,
                    )
                    stats.dates_written += 1
                    if stats.earliest_written is None or scan_date < stats.earliest_written:
                        stats.earliest_written = scan_date
                    if stats.latest_written is None or scan_date > stats.latest_written:
                        stats.latest_written = scan_date
                    if idx % 10 == 0 or idx == len(scan_dates):
                        logger.info(
                            "Launchpad backfill %s progress %d/%d written=%d failed=%d last=%s",
                            resolved_id,
                            idx,
                            len(scan_dates),
                            stats.dates_written,
                            stats.dates_failed,
                            scan_date,
                        )
                except Exception as exc:
                    stats.dates_failed += 1
                    msg = f"{resolved_id}/{scan_date}: {exc}"
                    stats.errors.append(msg)
                    logger.exception("Launchpad backfill failed for %s on %s", resolved_id, scan_date)

            if job_id is not None:
                status = "success" if stats.dates_failed == 0 else "failed"
                self.job_repo.finish_job(
                    job_id,
                    status=status,
                    tickers_fetched=len(universe),
                    tickers_failed=stats.dates_failed,
                    error_message="; ".join(stats.errors[:3]) if stats.errors else None,
                )

            logger.info("Launchpad backfill %s complete: %s", resolved_id, stats.summary())
            return stats

        except Exception:
            if job_id is not None:
                self.job_repo.finish_job(job_id, status="failed", error_message="backfill aborted")
            raise

    def coverage(
        self,
        *,
        universe_id: str,
        since: date,
        until: date | None = None,
    ) -> BackfillCoverage:
        until = until or date.today()
        scan_dates = iter_saturday_scan_dates(since, until)
        existing: list[date] = []
        for run in self.scan_repo.list_runs_filtered(
            strategy_id="launchpad",
            universe_id=universe_id,
            since=since,
            until=until,
        ):
            normalized = as_scan_date(run["scan_date"])
            if normalized is not None:
                existing.append(normalized)
        coverage = compute_backfill_coverage(since=since, until=until, existing_dates=existing)
        coverage.planned_dates = scan_dates
        return coverage

    def _backfill_one_date(
        self,
        *,
        scan_date: date,
        universe: list[str],
        resolved_id: str,
        prices_full: pd.DataFrame,
        spec,
        eligibility_mode: str,
        persist: bool,
    ) -> None:
        truncated_frames: list[pd.DataFrame] = []
        for ticker in prices_full["ticker"].unique():
            sub = prices_full[prices_full["ticker"] == ticker].copy()
            trimmed = truncate_daily_to_date(sub, scan_date)
            if trimmed is not None and not trimmed.empty:
                truncated_frames.append(trimmed)
        if not truncated_frames:
            raise RuntimeError(f"No truncated price rows for {scan_date}")

        prices = pd.concat(truncated_frames, ignore_index=True)
        ctx = ScanContext.from_prices(
            prices,
            universe=universe,
            eligibility_mode=eligibility_mode,
        )
        engine = StrategyEngine(
            spec,
            tickers=universe,
            context=ctx,
            eligibility_mode=eligibility_mode,
        )
        scan_result = engine.run()
        results = scan_result.to_dataframe()
        scores_by_ticker = ticker_results_to_legacy_scores(scan_result.tickers)
        as_of = max_bar_date(ctx.spy_df)
        scan_time = datetime.combine(scan_date, LAUNCHPAD_BATCH_TIME, tzinfo=ET)

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
            strategy_id="launchpad",
            eligibility_mode=eligibility_mode,
            data_provenance=build_data_provenance(
                strategy_id="launchpad",
                universe_id=resolved_id,
                scan_date=scan_date,
                price_cache="parquet",
                as_of_price=str(as_of) if as_of else str(scan_date),
                extra={
                    "backfill": True,
                    "backfill_version": BACKFILL_VERSION,
                    "lookback_days": ML_LABEL_LOOKBACK_DAYS,
                },
            ),
        )
        scan_report["data_provenance"]["scan_time_utc"] = scan_time.astimezone(
            ZoneInfo("UTC")
        ).isoformat()

        if persist:
            run_id = self.scan_repo.upsert_scan(
                scan_date=scan_date,
                strategy_id="launchpad",
                universe_id=resolved_id,
                report=scan_report,
                scan_time=scan_time.astimezone(ZoneInfo("UTC")),
            )
            logger.info(
                "Backfill persisted %s launchpad/%s run_id=%s actionable=%s",
                scan_date,
                resolved_id,
                run_id,
                scan_report["scan_summary"].get("actionable_count", 0),
            )
        else:
            logger.info(
                "Backfill dry-run %s launchpad/%s rows=%d actionable=%s",
                scan_date,
                resolved_id,
                len(results),
                scan_report["scan_summary"].get("actionable_count", 0),
            )


def _coverage_summary(coverage: BackfillCoverage, scan_dates: list[date], existing: set[date]) -> str:
    missing = [d for d in scan_dates if d not in existing]
    return (
        f"range={scan_dates[0] if scan_dates else None}..{scan_dates[-1] if scan_dates else None} "
        f"planned={len(scan_dates)} existing={len(existing)} missing={len(missing)}"
    )
