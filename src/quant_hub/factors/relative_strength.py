from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_hub.engine.context import ScanContext
from quant_hub.factors.base import make_factor_result
from quant_hub.scoring.relative_strength import (
    compute_rs_market_ratio,
    compute_rs_sector_ratio,
    score_rs_market,
    score_rs_sector,
)


@dataclass
class RsMarketFactor:
    name: str = "rs_market"
    pass_kind: str = "universe"

    def compute_universe(
        self,
        ctx: ScanContext,
        tickers: list[str],
    ) -> dict:
        ratios = pd.Series(
            {
                t: compute_rs_market_ratio(ctx.stock_dfs[t], ctx.spy_df)
                for t in tickers
            },
            dtype=float,
        )
        scores = score_rs_market(ratios)
        return {
            t: make_factor_result(self.name, scores.get(t, 0), 20.0, ratio=ratios.get(t))
            for t in tickers
        }


@dataclass
class RsSectorFactor:
    name: str = "rs_sector"
    pass_kind: str = "universe"

    def compute_universe(
        self,
        ctx: ScanContext,
        tickers: list[str],
    ) -> dict:
        ratios = pd.Series(
            {
                t: compute_rs_sector_ratio(ctx.stock_dfs[t], ctx.sector_df(t))
                for t in tickers
                if ctx.sector_df(t) is not None
            },
            dtype=float,
        )
        sector_etf_series = pd.Series({t: ctx.sector_etfs.get(t) for t in tickers})
        scores = score_rs_sector(ratios, sector_etf_series)
        return {
            t: make_factor_result(self.name, scores.get(t, 0), 15.0, ratio=ratios.get(t))
            for t in tickers
        }
