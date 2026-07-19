from __future__ import annotations

from quant_hub.engine.protocols import StrategySpec

STRATEGY_IDS = ("launchpad",)


def get_strategy(strategy_id: str) -> StrategySpec:
    if strategy_id == "launchpad":
        from quant_hub.strategies.launchpad.spec import LAUNCHPAD_STRATEGY

        return LAUNCHPAD_STRATEGY
    raise ValueError(f"Unknown strategy: {strategy_id}")
