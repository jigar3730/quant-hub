from __future__ import annotations

from dataclasses import dataclass

from quant_hub.engine.context import ScanContext
from quant_hub.factors.base import make_factor_result
from quant_hub.scoring.launchpad import (
    score_macd_zero_line,
    score_squeeze_intensity,
    score_tightness_percentile,
    score_volume_vacuum_depth,
    score_trend_proximity_match,
)


@dataclass
class MacdZeroLineFactor:
    """Tier-1 ignition gate (not counted toward the 100-pt raw score)."""

    name: str = "macd_zero_line"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score, details = score_macd_zero_line(df)
        return make_factor_result(self.name, score, 25.0, **details)


@dataclass
class SqueezeIntensityFactor:
    name: str = "squeeze_intensity"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score, details = score_squeeze_intensity(df)
        return make_factor_result(self.name, score, 40.0, **details)


@dataclass
class TightnessPercentileFactor:
    name: str = "tightness_percentile"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score, details = score_tightness_percentile(df)
        return make_factor_result(self.name, score, 15.0, **details)


@dataclass
class VolumeVacuumDepthFactor:
    name: str = "volume_vacuum_depth"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        score, details = score_volume_vacuum_depth(df)
        return make_factor_result(self.name, score, 30.0, **details)


@dataclass
class TrendProximityMatchFactor:
    name: str = "trend_proximity_match"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        df = ctx.stock_dfs[ticker]
        spy_df = ctx.spy_df
        score, details = score_trend_proximity_match(df, spy_df)
        return make_factor_result(self.name, score, 15.0, **details)
