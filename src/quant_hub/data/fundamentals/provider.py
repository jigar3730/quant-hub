from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

import pandas as pd
import yfinance as yf

from quant_hub.data.fundamentals.cache import FundamentalsCache
from quant_hub.data.fundamentals.compute import (
    eps_combined_growth,
    extract_income_series,
    revenue_yoy_blended,
)
from quant_hub.data.fundamentals.types import FundamentalsSnapshot

logger = logging.getLogger(__name__)

FETCH_PAUSE_SEC = 0.15


def fetch_fundamentals_snapshot(ticker: str) -> FundamentalsSnapshot:
    """Fetch and compute fundamentals for a single ticker."""
    ticker = ticker.upper()
    try:
        income = yf.Ticker(ticker).quarterly_income_stmt
        series = extract_income_series(income)
        revenue = series.get("revenue", pd.Series(dtype=float))
        eps = series.get("eps", pd.Series(dtype=float))
        op_inc = series.get("operating_income")
        net_inc = series.get("net_income")

        rev_val, rev_status, rev_source = revenue_yoy_blended(revenue)
        eps_combined, eps_status, eps_yoy, eps_cagr, eps_source = eps_combined_growth(
            eps,
            operating_income=op_inc,
            net_income=net_inc,
        )
        if rev_val is not None and rev_val < 0 and rev_status == "OK":
            rev_status = "NEGATIVE"
        if eps_combined is not None and eps_combined < 0 and eps_status == "OK":
            eps_status = "NEGATIVE"
        quarters = max(len(revenue), len(eps))

        return FundamentalsSnapshot(
            ticker=ticker,
            revenue_yoy=rev_val,
            revenue_yoy_status=rev_status,
            revenue_yoy_source=rev_source,
            eps_combined=eps_combined,
            eps_combined_status=eps_status,
            eps_yoy=eps_yoy,
            eps_cagr_3y=eps_cagr,
            eps_source=eps_source,
            quarters_available=quarters,
            fetched_at=datetime.now(UTC).isoformat(),
        )
    except Exception as exc:
        logger.warning("Could not fetch fundamentals for %s: %s", ticker, exc)
        return FundamentalsSnapshot.missing(ticker, error=str(exc))


def download_fundamentals(
    tickers: list[str],
    *,
    use_cache: bool = False,
    cache: FundamentalsCache | None = None,
) -> pd.DataFrame:
    """Download fundamentals for many tickers with optional JSON cache."""
    tickers = sorted(set(t.upper() for t in tickers))
    cache = cache or FundamentalsCache()
    cached_tickers, stale_tickers = cache.partition(tickers, use_cache=use_cache)

    snapshots: list[FundamentalsSnapshot] = []
    for ticker in cached_tickers:
        snap = cache.read(ticker)
        if snap is not None:
            snapshots.append(snap)
        else:
            stale_tickers.append(ticker)

    for i, ticker in enumerate(stale_tickers):
        snap = fetch_fundamentals_snapshot(ticker)
        snapshots.append(snap)
        if use_cache:
            cache.write(snap)
        if i + 1 < len(stale_tickers):
            time.sleep(FETCH_PAUSE_SEC)

    rows = [s.to_dict() for s in snapshots]
    if not rows:
        return pd.DataFrame(
            columns=[
                "ticker",
                "revenue_yoy",
                "revenue_yoy_status",
                "revenue_yoy_source",
                "eps_combined",
                "eps_combined_status",
                "eps_yoy",
                "eps_cagr_3y",
                "eps_source",
                "quarters_available",
                "fetched_at",
                "fetch_error",
            ]
        )
    return pd.DataFrame(rows)


def fundamentals_quality_summary(df: pd.DataFrame) -> dict:
    """Aggregate DQ metrics for scan metadata."""
    n = len(df)
    if n == 0:
        return {"tickers": 0}

    def _rate(status_col: str, ok_value: str = "OK") -> dict:
        if status_col not in df.columns:
            return {"ok": 0, "missing": n, "other": 0}
        col = df[status_col].fillna("MISSING")
        ok = int((col == ok_value).sum())
        missing = int((col == "MISSING").sum())
        other = n - ok - missing
        return {"ok": ok, "missing": missing, "other": other, "ok_pct": round(ok / n * 100, 1)}

    return {
        "tickers": n,
        "revenue": _rate("revenue_yoy_status"),
        "eps": _rate("eps_combined_status"),
        "avg_quarters": round(float(df["quarters_available"].mean()), 1) if "quarters_available" in df else 0,
        "fetch_errors": int(df["fetch_error"].notna().sum()) if "fetch_error" in df else 0,
    }
