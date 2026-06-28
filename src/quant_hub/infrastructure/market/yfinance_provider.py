from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from quant_hub.config import LOOKBACK_DAYS
from quant_hub.data.fundamentals_helpers import cagr, quarterly_series
from quant_hub.data.quality import sanitize_growth_rate
from quant_hub.infrastructure.cache.parquet_cache import OHLCV_COLUMNS, ParquetCache

logger = logging.getLogger(__name__)

CHUNK_SIZE = 50
CHUNK_PAUSE_SEC = 1.0


def _normalize_date_column(df: pd.DataFrame) -> pd.DataFrame:
    if "Date" in df.columns:
        return df
    for candidate in ("index", "Datetime", "date"):
        if candidate in df.columns:
            return df.rename(columns={candidate: "Date"})
    return df


def _download_chunk(tickers: list[str], start: str) -> pd.DataFrame:
    raw = yf.download(
        tickers,
        start=start,
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    frames: list[pd.DataFrame] = []
    if isinstance(raw.columns, pd.MultiIndex):
        for ticker in tickers:
            if ticker not in raw.columns.get_level_values(0):
                logger.warning("No price data for %s", ticker)
                continue
            sub = raw[ticker].dropna(how="all")
            if sub.empty:
                continue
            sub = sub.reset_index()
            sub = _normalize_date_column(sub)
            sub["ticker"] = ticker
            frames.append(sub)
    elif not raw.empty:
        sub = raw.reset_index()
        sub = _normalize_date_column(sub)
        sub["ticker"] = tickers[0]
        frames.append(sub)

    if not frames:
        return pd.DataFrame(columns=["Date", *OHLCV_COLUMNS, "ticker"])

    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={"Adj Close": "Close"})
    return df[["Date", *OHLCV_COLUMNS, "ticker"]]


def download_prices(
    tickers: list[str],
    *,
    use_cache: bool = False,
    lookback_days: int = LOOKBACK_DAYS,
    cache: ParquetCache | None = None,
) -> pd.DataFrame:
    """Download daily OHLCV; per-ticker parquet cache with chunked yfinance fetch."""
    tickers = sorted(set(tickers))
    cache = cache or ParquetCache()
    cached_tickers, stale_tickers = cache.partition(tickers, use_cache=use_cache)

    frames: list[pd.DataFrame] = []
    if cached_tickers:
        frames.append(cache.read_many(cached_tickers))

    if stale_tickers:
        start = (datetime.now() - timedelta(days=int(lookback_days * 1.6))).strftime("%Y-%m-%d")
        for i in range(0, len(stale_tickers), CHUNK_SIZE):
            chunk = stale_tickers[i : i + CHUNK_SIZE]
            chunk_df = _download_chunk(chunk, start)
            if chunk_df.empty:
                continue
            frames.append(chunk_df)
            if use_cache:
                for ticker in chunk:
                    sub = chunk_df[chunk_df["ticker"] == ticker]
                    if not sub.empty:
                        cache.write(ticker, sub)
            if i + CHUNK_SIZE < len(stale_tickers):
                time.sleep(CHUNK_PAUSE_SEC)

    if not frames:
        return pd.DataFrame(columns=["Date", *OHLCV_COLUMNS, "ticker"])

    df = pd.concat(frames, ignore_index=True)
    return df[df["ticker"].isin(tickers)].copy()


def _yoy_growth(series: pd.Series, quarters_back: int = 4) -> float | None:
    if len(series) <= quarters_back:
        return None
    recent = series.iloc[-1]
    prior = series.iloc[-1 - quarters_back]
    if prior <= 0 or pd.isna(prior) or pd.isna(recent):
        return None
    return sanitize_growth_rate((recent / prior) - 1)


def download_fundamentals(
    tickers: list[str],
    *,
    use_cache: bool = False,
) -> pd.DataFrame:
    """Download quarterly revenue and EPS fundamentals per ticker (no cache in v1)."""
    del use_cache  # fundamentals cache deferred to v1.1
    tickers = sorted(set(tickers))
    rows: list[dict] = []
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            income = t.quarterly_income_stmt
            revenue = quarterly_series(income, "Total Revenue")
            if revenue.empty:
                revenue = quarterly_series(income, "Revenue")
            eps = quarterly_series(income, "Diluted EPS")
            if eps.empty:
                eps = quarterly_series(income, "Basic EPS")

            revenue_yoy = _yoy_growth(revenue)
            revenue_yoy_2q = None
            if len(revenue) > 5:
                g1 = _yoy_growth(revenue)
                g2 = (
                    (revenue.iloc[-2] / revenue.iloc[-6] - 1)
                    if revenue.iloc[-6] > 0
                    else None
                )
                if g1 is not None and g2 is not None:
                    revenue_yoy_2q = (g1 + g2) / 2
                else:
                    revenue_yoy_2q = g1

            eps_yoy = _yoy_growth(eps)
            eps_cagr_3y = sanitize_growth_rate(cagr(eps, years=3.0))
            combined_eps = None
            if eps_yoy is not None and eps_cagr_3y is not None:
                combined_eps = 0.7 * eps_yoy + 0.3 * eps_cagr_3y
            elif eps_yoy is not None:
                combined_eps = eps_yoy

            rows.append(
                {
                    "ticker": ticker,
                    "revenue_yoy": revenue_yoy_2q if revenue_yoy_2q is not None else revenue_yoy,
                    "eps_combined": combined_eps,
                }
            )
        except Exception:
            logger.warning("Could not fetch fundamentals for %s", ticker)
            rows.append({"ticker": ticker, "revenue_yoy": None, "eps_combined": None})

    return pd.DataFrame(rows)
