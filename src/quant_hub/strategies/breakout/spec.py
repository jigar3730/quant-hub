from __future__ import annotations

from dataclasses import dataclass

from quant_hub.config import RAW_SCORE_MAX
from quant_hub.engine.protocols import FactorBinding, StrategySpec
from quant_hub.engine.types import TickerResult
from quant_hub.factors import (
    AccumulationFactor,
    CompressionFactor,
    EpsFactor,
    PatternFactor,
    RelativeVolumeFactor,
    ResistanceFactor,
    RevenueFactor,
    RsMarketFactor,
    RsSectorFactor,
)
from quant_hub.regime.market import MarketRegime
from quant_hub.strategies.breakout.aggregate import (
    BREAKOUT_SCORE_COLUMNS,
    aggregate_breakout_ticker,
)
from quant_hub.strategies.breakout.filters import BreakoutEligibilityFilter
from quant_hub.strategies.breakout.tiers import assign_tier


@dataclass(frozen=True)
class BreakoutStrategySpec(StrategySpec):
    def aggregate(self, ticker: TickerResult, regime: MarketRegime) -> TickerResult:
        return aggregate_breakout_ticker(ticker, regime)

    def assign_tier(self, ticker: TickerResult) -> str:
        return assign_tier(ticker)


BREAKOUT_STRATEGY = BreakoutStrategySpec(
    id="breakout",
    name="Breakout Scanner",
    max_raw_score=float(RAW_SCORE_MAX),
    filters=[BreakoutEligibilityFilter()],
    factor_bindings=[
        FactorBinding(RsMarketFactor()),
        FactorBinding(RsSectorFactor()),
        FactorBinding(AccumulationFactor()),
        FactorBinding(RelativeVolumeFactor()),
        FactorBinding(CompressionFactor()),
        FactorBinding(PatternFactor()),
        FactorBinding(ResistanceFactor()),
        FactorBinding(RevenueFactor()),
        FactorBinding(EpsFactor()),
    ],
    regime_mode="multiplier",
    penalties=[],
    sort_keys=["final_adjusted_score", "rs_market_score", "accumulation_score"],
    score_columns=BREAKOUT_SCORE_COLUMNS,
)
