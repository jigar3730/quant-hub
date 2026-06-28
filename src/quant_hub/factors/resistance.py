from __future__ import annotations

from dataclasses import dataclass

from quant_hub.engine.context import ScanContext
from quant_hub.factors.base import make_factor_result
from quant_hub.scoring.resistance import score_resistance


@dataclass
class ResistanceFactor:
    name: str = "resistance"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score = score_resistance(df)
        return make_factor_result(self.name, score, 10.0)
