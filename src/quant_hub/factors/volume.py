from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_hub.engine.context import ScanContext
from quant_hub.factors.base import make_factor_result
from quant_hub.scoring.volume import (
    compute_accumulation_ratio,
    score_accumulation,
    score_relative_volume,
)


@dataclass
class AccumulationFactor:
    name: str = "accumulation"
    pass_kind: str = "universe"

    def compute_universe(
        self,
        ctx: ScanContext,
        tickers: list[str],
    ) -> dict:
        ratios = pd.Series(
            {t: compute_accumulation_ratio(ctx.stock_dfs[t]) for t in tickers},
            dtype=float,
        )
        scores = score_accumulation(ratios)
        return {
            t: make_factor_result(self.name, scores.get(t, 0), 12.0, ratio=ratios.get(t))
            for t in tickers
        }


@dataclass
class RelativeVolumeFactor:
    name: str = "relative_volume"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str) -> dict:
        df = ctx.stock_dfs[ticker]
        score = score_relative_volume(df)
        return make_factor_result(self.name, score, 8.0)
