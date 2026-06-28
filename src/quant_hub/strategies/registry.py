from __future__ import annotations

from quant_hub.engine.protocols import StrategySpec

STRATEGY_IDS = ("breakout",)


def get_strategy(strategy_id: str) -> StrategySpec:
    if strategy_id == "breakout":
        from quant_hub.strategies.breakout.spec import BREAKOUT_STRATEGY

        return BREAKOUT_STRATEGY
    raise ValueError(f"Unknown strategy: {strategy_id}")
