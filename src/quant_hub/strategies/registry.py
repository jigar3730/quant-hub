from __future__ import annotations

from quant_hub.engine.protocols import StrategySpec

STRATEGY_IDS = ("breakout", "launchpad")


def get_strategy(strategy_id: str) -> StrategySpec:
    if strategy_id == "breakout":
        from quant_hub.strategies.breakout.spec import BREAKOUT_STRATEGY

        return BREAKOUT_STRATEGY
    if strategy_id == "launchpad":
        from quant_hub.strategies.launchpad.spec import LAUNCHPAD_STRATEGY

        return LAUNCHPAD_STRATEGY
    raise ValueError(f"Unknown strategy: {strategy_id}")
