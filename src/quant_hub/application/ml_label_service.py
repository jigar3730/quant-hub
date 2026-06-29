"""Compute forward-return labels from cached OHLCV."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from quant_hub.config import (
    BENCHMARK_TICKER_FOR_LABELS,
    DEFAULT_LABEL_HORIZONS,
    LABEL_RETURN_THRESHOLD_PCT,
    ML_LABEL_CACHE_SUBDIR,
    ML_LABEL_CACHE_TTL_HOURS,
    PRICE_CACHE_SUBDIR,
)
from quant_hub.infrastructure.cache.parquet_cache import ParquetCache
from quant_hub.infrastructure.postgres.outcomes_repository import OutcomesRepository
from quant_hub.infrastructure.postgres.repository import ScanRepository
from quant_hub.ml.labels import anchor_date_from_run, compute_forward_outcome

logger = logging.getLogger(__name__)


@dataclass
class LabelRunStats:
    runs_processed: int = 0
    tickers_processed: int = 0
    outcomes_written: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)

    def summary(self) -> str:
        parts = [
            f"runs={self.runs_processed}",
            f"tickers={self.tickers_processed}",
            f"outcomes={self.outcomes_written}",
        ]
        if self.status_counts:
            status = ", ".join(f"{k}={v}" for k, v in sorted(self.status_counts.items()))
            parts.append(f"status[{status}]")
        return " ".join(parts)


class MLLabelService:
    def __init__(
        self,
        *,
        scan_repo: ScanRepository | None = None,
        outcomes_repo: OutcomesRepository | None = None,
        price_cache: ParquetCache | None = None,
    ) -> None:
        self.scan_repo = scan_repo or ScanRepository()
        self.outcomes_repo = outcomes_repo or OutcomesRepository()
        if price_cache is not None:
            self._primary_cache = price_cache
            self._fallback_cache = None
        else:
            self._primary_cache = ParquetCache(
                base_dir=ML_LABEL_CACHE_SUBDIR,
                ttl_hours=ML_LABEL_CACHE_TTL_HOURS,
            )
            self._fallback_cache = ParquetCache(base_dir=PRICE_CACHE_SUBDIR)

    def _read_prices(self, ticker: str):
        df = self._primary_cache.read(ticker)
        if (df is None or df.empty) and self._fallback_cache is not None:
            df = self._fallback_cache.read(ticker)
        return df

    def run(
        self,
        *,
        run_id: int | None = None,
        strategy_id: str | None = None,
        universe_id: str | None = None,
        since: date | None = None,
        until: date | None = None,
        horizons: tuple[int, ...] = DEFAULT_LABEL_HORIZONS,
        return_threshold_pct: float = LABEL_RETURN_THRESHOLD_PCT,
        benchmark_ticker: str = BENCHMARK_TICKER_FOR_LABELS,
    ) -> LabelRunStats:
        stats = LabelRunStats()
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
            logger.warning("No scan runs matched label filters")
            return stats

        spy_df = self._read_prices(benchmark_ticker)
        if spy_df is None or spy_df.empty:
            logger.warning("Benchmark %s not in price cache; excess returns will be null", benchmark_ticker)

        for run in runs:
            stats.runs_processed += 1
            anchor = anchor_date_from_run(run)
            details = self.scan_repo.list_ticker_details_for_run(run["id"])
            for detail in details:
                ticker = detail.get("ticker")
                if not ticker:
                    continue
                stats.tickers_processed += 1
                price_df = self._read_prices(ticker)
                outcome_rows = []
                for horizon in horizons:
                    outcome = compute_forward_outcome(
                        price_df,
                        anchor_date=anchor,
                        horizon_days=horizon,
                        spy_df=spy_df,
                        return_threshold_pct=return_threshold_pct,
                    )
                    outcome_rows.append(outcome.to_dict())
                    stats.status_counts[outcome.label_status] = (
                        stats.status_counts.get(outcome.label_status, 0) + 1
                    )
                written = self.outcomes_repo.upsert_outcomes(
                    run_id=run["id"],
                    ticker=ticker,
                    rows=outcome_rows,
                )
                stats.outcomes_written += written

        logger.info("ML label job complete: %s", stats.summary())
        return stats
