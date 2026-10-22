"""Warm long daily price history for research backtests (sector ETFs + benchmarks)."""

from __future__ import annotations

import logging
from collections.abc import Callable

import pandas as pd

from quant_hub.application.universe_service import UniverseService
from quant_hub.config import (
    RESEARCH_BENCHMARKS,
    RESEARCH_CACHE_TTL_HOURS,
    RESEARCH_CONTEXT_SERIES,
    RESEARCH_ETF_UNIVERSE,
    RESEARCH_LOOKBACK_DAYS,
    RESEARCH_PRICE_DIR,
)
from quant_hub.infrastructure.cache.parquet_cache import ParquetCache
from quant_hub.infrastructure.market.yfinance_prices import download_prices

logger = logging.getLogger(__name__)

COVERAGE_COLUMNS = ["ticker", "first_date", "last_date", "bars", "nan_close_share"]


def coverage_table(prices: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """One row per requested ticker; tickers with no data get bars=0."""
    rows = []
    for ticker in tickers:
        sub = prices[prices["ticker"] == ticker] if not prices.empty else prices
        if sub.empty:
            rows.append((ticker, None, None, 0, None))
            continue
        dates = pd.to_datetime(sub["Date"])
        rows.append(
            (
                ticker,
                dates.min().date(),
                dates.max().date(),
                len(sub),
                float(sub["Close"].isna().mean()),
            )
        )
    return pd.DataFrame(rows, columns=COVERAGE_COLUMNS)


class ResearchDataService:
    """Populate the research price cache used by backtests."""

    def __init__(
        self,
        *,
        universe_service: UniverseService | None = None,
        downloader: Callable[..., pd.DataFrame] = download_prices,
        cache: ParquetCache | None = None,
    ) -> None:
        self.universe_service = universe_service or UniverseService()
        self.downloader = downloader
        self.cache = cache or ParquetCache(
            base_dir=RESEARCH_PRICE_DIR,
            ttl_hours=RESEARCH_CACHE_TTL_HOURS,
        )

    def etf_tickers(self) -> list[str]:
        _resolved_id, universe = self.universe_service.resolve(universe_id=RESEARCH_ETF_UNIVERSE)
        return sorted(set(universe) | set(RESEARCH_BENCHMARKS) | set(RESEARCH_CONTEXT_SERIES))

    def warm_etf_history(self, *, force_refresh: bool = False) -> pd.DataFrame:
        tickers = self.etf_tickers()
        logger.info(
            "Warming research history (%d tickers, lookback=%dd)",
            len(tickers),
            RESEARCH_LOOKBACK_DAYS,
        )
        prices = self.downloader(
            tickers,
            use_cache=not force_refresh,
            lookback_days=RESEARCH_LOOKBACK_DAYS,
            cache=self.cache,
        )
        return coverage_table(prices, tickers)
