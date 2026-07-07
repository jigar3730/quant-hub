from __future__ import annotations

from dataclasses import dataclass

from quant_hub.engine.context import ScanContext
from quant_hub.factors.base import make_factor_result
from quant_hub.scoring.launchpad import (
    score_atr_contraction,
    score_ma_tightness,
    score_macd_zero_line,
    score_swing_low_vcp,
    score_volume_dry_up,
)


@dataclass
class MacdZeroLineFactor:
    name: str = "macd_zero_line"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score, details = score_macd_zero_line(df)
        return make_factor_result(self.name, score, 25.0, **details)


@dataclass
class MaTightnessFactor:
    name: str = "ma_tightness"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score, details = score_ma_tightness(df)
        return make_factor_result(self.name, score, 25.0, **details)


@dataclass
class AtrContractionFactor:
    name: str = "atr_contraction"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score, details = score_atr_contraction(df)
        return make_factor_result(self.name, score, 20.0, **details)


@dataclass
class VolumeDryUpFactor:
    name: str = "volume_dry_up"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score, details = score_volume_dry_up(df)
        return make_factor_result(self.name, score, 15.0, **details)


@dataclass
class SwingLowVcpFactor:
    name: str = "swing_low_vcp"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score, details = score_swing_low_vcp(df)
        return make_factor_result(self.name, score, 15.0, **details)
