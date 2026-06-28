from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from quant_hub.config import ALL_SECTOR_ETFS, BENCHMARK_TICKER
from quant_hub.infrastructure.market.yfinance_provider import (
    download_fundamentals,
    download_prices,
    fundamentals_quality_summary,
)
from quant_hub.regime.market import MarketRegime, compute_market_regime, regime_detail


def ticker_df(prices: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    sub = prices[prices["ticker"] == ticker].copy()
    if sub.empty:
        return None
    return sub.sort_values("Date").reset_index(drop=True)


def synthetic_prices(tickers: list[str]) -> pd.DataFrame:
    """Generate synthetic OHLCV for dry-run mode."""
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=260)
    frames = []
    rng = np.random.default_rng(42)
    for i, ticker in enumerate(tickers):
        base = 50 + i * 5
        noise = rng.normal(0, 0.5, len(dates)).cumsum()
        close = base + noise + np.linspace(0, 20, len(dates))
        high = close + rng.uniform(0.5, 2, len(dates))
        low = close - rng.uniform(0.5, 2, len(dates))
        open_ = close + rng.uniform(-1, 1, len(dates))
        volume = rng.integers(1_000_000, 3_000_000, len(dates))
        frames.append(
            pd.DataFrame(
                {
                    "Date": dates,
                    "Open": open_,
                    "High": high,
                    "Low": low,
                    "Close": close,
                    "Volume": volume,
                    "ticker": ticker,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def synthetic_fundamentals(tickers: list[str]) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        rows.append(
            {
                "ticker": ticker,
                "revenue_yoy": 0.25,
                "revenue_yoy_status": "OK",
                "revenue_yoy_source": "synthetic",
                "eps_combined": 0.35,
                "eps_combined_status": "OK",
                "eps_yoy": 0.30,
                "eps_cagr_3y": 0.25,
                "eps_source": "synthetic",
                "quarters_available": 8,
                "fetched_at": "",
                "fetch_error": None,
            }
        )
    return pd.DataFrame(rows)


@dataclass
class ScanContext:
    universe: list[str]
    stock_dfs: dict[str, pd.DataFrame]
    spy_df: pd.DataFrame
    sector_dfs: dict[str, pd.DataFrame]
    fund_map: dict[str, dict[str, Any]]
    sector_etfs: dict[str, str]
    regime: MarketRegime
    regime_detail: dict[str, Any]
    dry_run: bool = False
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_universe(
        cls,
        *,
        tickers: list[str] | None = None,
        tickers_file=None,
        dynamic_universe: bool = False,
        use_cache: bool = False,
        dry_run: bool = False,
        eligibility_mode: str = "stock",
    ) -> ScanContext:
        if not tickers:
            raise ValueError("ScanContext requires an explicit ticker list")
        universe = list(tickers)
        download_tickers = sorted(set(universe) | set(ALL_SECTOR_ETFS) | {BENCHMARK_TICKER})

        if dry_run:
            prices = synthetic_prices(download_tickers)
            fundamentals = synthetic_fundamentals(universe)
            fund_quality = fundamentals_quality_summary(fundamentals)
        else:
            prices = download_prices(download_tickers, use_cache=use_cache)
            fundamentals = download_fundamentals(universe, use_cache=use_cache)
            fund_quality = fundamentals_quality_summary(fundamentals)

        spy_df = ticker_df(prices, BENCHMARK_TICKER)
        if spy_df is None or spy_df.empty:
            raise RuntimeError(f"Missing benchmark data for {BENCHMARK_TICKER}")

        regime = compute_market_regime(spy_df)
        regime_info = regime_detail(spy_df)
        fund_map = fundamentals.set_index("ticker").to_dict(orient="index")
        sector_dfs = {etf: ticker_df(prices, etf) for etf in ALL_SECTOR_ETFS}

        stock_dfs: dict[str, pd.DataFrame] = {}
        for ticker in universe:
            df = ticker_df(prices, ticker)
            if df is not None and not df.empty:
                stock_dfs[ticker] = df

        return cls(
            universe=universe,
            stock_dfs=stock_dfs,
            spy_df=spy_df,
            sector_dfs=sector_dfs,
            fund_map=fund_map,
            sector_etfs={},
            regime=regime,
            regime_detail=regime_info,
            dry_run=dry_run,
            extras={"fundamentals_quality": fund_quality, "eligibility_mode": eligibility_mode},
        )

    def stock_df(self, ticker: str) -> pd.DataFrame | None:
        return self.stock_dfs.get(ticker)

    def sector_df(self, ticker: str) -> pd.DataFrame | None:
        etf = self.sector_etfs.get(ticker)
        if etf is None:
            return None
        return self.sector_dfs.get(etf)

    def fundamentals(self, ticker: str) -> dict[str, Any]:
        return self.fund_map.get(ticker, {})
