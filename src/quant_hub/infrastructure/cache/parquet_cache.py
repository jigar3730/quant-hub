from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from quant_hub.config import CACHE_TTL_HOURS, PRICE_CACHE_SUBDIR

logger = logging.getLogger(__name__)

OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


class ParquetCache:
    def __init__(
        self,
        base_dir: Path | None = None,
        *,
        ttl_hours: float = CACHE_TTL_HOURS,
    ) -> None:
        self.base_dir = base_dir or PRICE_CACHE_SUBDIR
        self.ttl = timedelta(hours=ttl_hours)

    def path_for(self, ticker: str) -> Path:
        return self.base_dir / f"{ticker.upper()}.parquet"

    def is_fresh(self, ticker: str, *, max_bar_age_days: int | None = None) -> bool:
        path = self.path_for(ticker)
        if not path.exists():
            return False
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        if datetime.now() - mtime >= self.ttl:
            return False
        if max_bar_age_days is not None:
            from quant_hub.data.quality import ohlcv_is_stale

            df = self.read(ticker)
            if ohlcv_is_stale(df, max_age_days=max_bar_age_days):
                return False
        return True

    def read(self, ticker: str) -> pd.DataFrame | None:
        path = self.path_for(ticker)
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
            if "Date" in df.columns:
                df["Date"] = pd.to_datetime(df["Date"])
            df["ticker"] = ticker.upper()
            return df
        except Exception:
            logger.warning("Failed to read cache for %s", ticker)
            return None

    def write(self, ticker: str, df: pd.DataFrame) -> None:
        path = self.path_for(ticker)
        path.parent.mkdir(parents=True, exist_ok=True)
        out = df.copy()
        if "ticker" not in out.columns:
            out["ticker"] = ticker.upper()
        out.to_parquet(path, index=False)

    def partition(
        self,
        tickers: list[str],
        *,
        use_cache: bool,
        max_bar_age_days: int | None = None,
    ) -> tuple[list[str], list[str]]:
        if not use_cache:
            return [], tickers
        cached: list[str] = []
        stale: list[str] = []
        for ticker in tickers:
            if self.is_fresh(ticker, max_bar_age_days=max_bar_age_days):
                cached.append(ticker)
            else:
                stale.append(ticker)
        if cached:
            logger.info("Cache hits: %d/%d tickers", len(cached), len(tickers))
        if stale:
            logger.info("Cache misses: %d tickers to fetch", len(stale))
        return cached, stale

    def read_many(self, tickers: list[str]) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for ticker in tickers:
            df = self.read(ticker)
            if df is not None and not df.empty:
                frames.append(df)
        if not frames:
            return pd.DataFrame(columns=["Date", *OHLCV_COLUMNS, "ticker"])
        return pd.concat(frames, ignore_index=True)
