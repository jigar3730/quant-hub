from __future__ import annotations

import logging
import time
from datetime import datetime

import pandas as pd
import yfinance as yf

from quant_hub.config import CACHE_TTL_WEEKLY_HOURS, SWING_INTERVAL, SWING_PERIOD, WEEKLY_CACHE_SUBDIR
from quant_hub.infrastructure.cache.parquet_cache import OHLCV_COLUMNS, ParquetCache

logger = logging.getLogger(__name__)

CHUNK_SIZE = 25
CHUNK_PAUSE_SEC = 1.0


def _normalize_weekly_df(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    df = raw.reset_index()
    if "Date" not in df.columns:
        for candidate in ("index", "Datetime", "date"):
            if candidate in df.columns:
                df = df.rename(columns={candidate: "Date"})
                break
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.rename(columns={"Adj Close": "Close"})
    cols = [c for c in ["Date", *OHLCV_COLUMNS] if c in df.columns or c == "Date"]
    df = df[[c for c in cols if c in df.columns]]
    # Drop incomplete current week (finance-vibe hygiene)
    if not df.empty and SWING_INTERVAL == "1wk":
        last = df["Date"].iloc[-1]
        if last.weekday() != 4:
            df = df.iloc[:-1]
    df["ticker"] = ticker.upper()
    return df


def _download_chunk(tickers: list[str]) -> pd.DataFrame:
    raw = yf.download(
        tickers,
        period=SWING_PERIOD,
        interval=SWING_INTERVAL,
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    frames: list[pd.DataFrame] = []
    if isinstance(raw.columns, pd.MultiIndex):
        for ticker in tickers:
            if ticker not in raw.columns.get_level_values(0):
                logger.warning("No weekly data for %s", ticker)
                continue
            sub = raw[ticker].dropna(how="all")
            if sub.empty:
                continue
            frames.append(_normalize_weekly_df(sub, ticker))
    elif not raw.empty and tickers:
        frames.append(_normalize_weekly_df(raw, tickers[0]))
    if not frames:
        return pd.DataFrame(columns=["Date", *OHLCV_COLUMNS, "ticker"])
    return pd.concat(frames, ignore_index=True)


def download_weekly_prices(
    tickers: list[str],
    *,
    use_cache: bool = True,
    force_refresh: bool = False,
) -> dict[str, pd.DataFrame]:
    """Fetch 10y / 1wk OHLCV per ticker with weekly parquet cache."""
    tickers = sorted(set(tickers))
    cache = ParquetCache(base_dir=WEEKLY_CACHE_SUBDIR, ttl_hours=CACHE_TTL_WEEKLY_HOURS)
    use_cache = use_cache and not force_refresh
    cached_tickers, stale_tickers = cache.partition(tickers, use_cache=use_cache)

    out: dict[str, pd.DataFrame] = {}
    for ticker in cached_tickers:
        df = cache.read(ticker)
        if df is not None and not df.empty:
            out[ticker] = df.drop(columns=["ticker"], errors="ignore")

    if stale_tickers:
        for i in range(0, len(stale_tickers), CHUNK_SIZE):
            chunk = stale_tickers[i : i + CHUNK_SIZE]
            chunk_df = _download_chunk(chunk)
            if chunk_df.empty:
                continue
            for ticker in chunk:
                sub = chunk_df[chunk_df["ticker"] == ticker].copy()
                if sub.empty:
                    continue
                sub = sub.drop(columns=["ticker"], errors="ignore")
                out[ticker] = sub
                if use_cache:
                    cache.write(ticker, sub)
            if i + CHUNK_SIZE < len(stale_tickers):
                time.sleep(CHUNK_PAUSE_SEC)

    return out
