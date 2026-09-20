"""R7 position sizing and trade-plan assembly."""

from __future__ import annotations

import math

from quant_hub.sector_swing.config import SwingParams
from quant_hub.sector_swing.models import SwingIndicators, TradePlan


def position_size(
    equity: float,
    risk_pct: float,
    max_position_pct: float,
    entry: float,
    risk_per_share: float,
) -> int:
    """floor(min(risk-limited, cap-limited)); 0 for any non-positive input."""
    if equity <= 0 or entry <= 0 or risk_per_share <= 0:
        return 0
    risk_limited = equity * risk_pct / risk_per_share
    cap_limited = equity * max_position_pct / entry
    return max(0, math.floor(min(risk_limited, cap_limited) + 1e-9))


def build_trade_plan(
    ind: SwingIndicators,
    params: SwingParams,
    *,
    stop: float,
    risk_per_share: float,
    equity: float,
    risk_pct: float,
    regime_blocked: bool = False,
) -> TradePlan:
    shares = position_size(equity, risk_pct, params.max_position_pct, ind.close, risk_per_share)
    return TradePlan(
        entry_ref=ind.close,
        stop=stop,
        risk_per_share=risk_per_share,
        stop_atr_multiple=risk_per_share / ind.atr14,
        target_2r=ind.close + params.target_r * risk_per_share,
        chase_limit=ind.close + params.chase_atr * ind.atr14,
        invalidation=stop,
        shares=shares,
        risk_dollars=shares * risk_per_share,
        position_dollars=shares * ind.close,
        regime_blocked=regime_blocked,
    )
