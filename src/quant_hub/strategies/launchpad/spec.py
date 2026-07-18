from __future__ import annotations

from dataclasses import dataclass

from quant_hub.config import LAUNCHPAD_RAW_SCORE_MAX
from quant_hub.engine.protocols import FactorBinding, StrategySpec
from quant_hub.engine.types import TickerResult
from quant_hub.factors.launchpad import (
    SqueezeIntensityFactor,
    TightnessPercentileFactor,
    VolumeVacuumDepthFactor,
    TrendProximityMatchFactor,
)
from quant_hub.regime.market import MarketRegime
from quant_hub.strategies.launchpad.aggregate import (
    LAUNCHPAD_SCORE_COLUMNS,
    aggregate_launchpad_ticker,
)
from quant_hub.strategies.launchpad.filters import LaunchpadEligibilityFilter
from quant_hub.strategies.launchpad.tiers import assign_tier


@dataclass(frozen=True)
class LaunchpadStrategySpec(StrategySpec):
    def aggregate(self, ticker: TickerResult, regime: MarketRegime) -> TickerResult:
        return aggregate_launchpad_ticker(ticker, regime)

    def assign_tier(self, ticker: TickerResult) -> str:
        return assign_tier(ticker)


LAUNCHPAD_STRATEGY = LaunchpadStrategySpec(
    id="launchpad",
    name="Launchpad Reversal",
    max_raw_score=float(LAUNCHPAD_RAW_SCORE_MAX),
    filters=[LaunchpadEligibilityFilter()],
    factor_bindings=[
        FactorBinding(SqueezeIntensityFactor()),
        FactorBinding(TightnessPercentileFactor()),
        FactorBinding(VolumeVacuumDepthFactor()),
        FactorBinding(TrendProximityMatchFactor()),
    ],
    regime_mode="none",
    penalties=[],
    sort_keys=["final_score", "squeeze_intensity_score", "volume_vacuum_depth_score"],
    score_columns=LAUNCHPAD_SCORE_COLUMNS,
)
