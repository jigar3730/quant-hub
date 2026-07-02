"""Warm extended daily price cache for ML forward-return labels."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from quant_hub.application.universe_service import UniverseService
from quant_hub.config import (
    BENCHMARK_TICKER_FOR_LABELS,
    ML_LABEL_CACHE_SUBDIR,
    ML_LABEL_CACHE_TTL_HOURS,
    ML_LABEL_LOOKBACK_DAYS,
    PRIMARY_INDEX_UNIVERSE,
)
from quant_hub.infrastructure.cache.parquet_cache import ParquetCache
from quant_hub.infrastructure.market.yfinance_prices import download_prices

logger = logging.getLogger(__name__)


@dataclass
class MLCacheWarmStats:
    tickers_requested: int = 0
    rows_fetched: int = 0

    def summary(self) -> str:
        return f"tickers={self.tickers_requested} rows={self.rows_fetched}"


class MLCacheService:
    """Populate long-horizon daily OHLCV used by quant-ml label."""

    def __init__(self, *, universe_service: UniverseService | None = None) -> None:
        self.universe_service = universe_service or UniverseService()
        self.cache = ParquetCache(
            base_dir=ML_LABEL_CACHE_SUBDIR,
            ttl_hours=ML_LABEL_CACHE_TTL_HOURS,
        )

    def warm_daily_prices(
        self,
        *,
        universe_id: str = PRIMARY_INDEX_UNIVERSE,
        force_refresh: bool = False,
    ) -> MLCacheWarmStats:
        _resolved_id, universe = self.universe_service.resolve(universe_id=universe_id)
        tickers = sorted(set(universe) | {BENCHMARK_TICKER_FOR_LABELS})
        stats = MLCacheWarmStats(tickers_requested=len(tickers))

        logger.info(
            "Warming ML label cache for %s (%d tickers, lookback=%dd)",
            universe_id,
            len(tickers),
            ML_LABEL_LOOKBACK_DAYS,
        )

        df = download_prices(
            tickers,
            use_cache=not force_refresh,
            lookback_days=ML_LABEL_LOOKBACK_DAYS,
            cache=self.cache,
        )
        stats.rows_fetched = len(df)
        logger.info("ML label cache warm complete: %s", stats.summary())
        return stats
