from __future__ import annotations

from dataclasses import dataclass

from quant_hub.engine.context import ScanContext
from quant_hub.factors.base import make_factor_result
from quant_hub.scoring.volatility import score_bollinger_compression, score_pattern_quality

COMPRESSION_MAX_SCORE = 15.0
PATTERN_MAX_SCORE = 5.0


@dataclass
class CompressionFactor:
    name: str = "compression"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score = score_bollinger_compression(df)
        return make_factor_result(self.name, score, COMPRESSION_MAX_SCORE)


@dataclass
class PatternFactor:
    name: str = "pattern"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score = score_pattern_quality(df)
        return make_factor_result(self.name, score, PATTERN_MAX_SCORE)
