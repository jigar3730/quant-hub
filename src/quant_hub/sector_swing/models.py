"""Small value types shared by the runner and report builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class RuleResult:
    """One evaluated rule; serialised into ``detail.eligibility.checks``."""

    rule: str
    passed: bool
    value: float | str | None
    threshold: str

    def to_dict(self) -> dict[str, Any]:
        value = self.value
        if isinstance(value, float):
            value = round(value, 4)
        return {
            "rule": self.rule,
            "passed": bool(self.passed),
            "value": value,
            "threshold": self.threshold,
        }


@dataclass(frozen=True)
class SwingIndicators:
    """Per-ticker indicators, computed once and shared by every rule."""

    bar_date: date
    close: float
    prev_high: float
    ema10: float
    ema20: float
    sma50: float
    atr14: float
    adx14: float
    lows_recent: tuple[float, ...]  # last PULLBACK_LOOKBACK bar lows, oldest first
    ema20_recent: tuple[float, ...]  # EMA(20) on those same bars
    avg_dollar_volume: float
    ret_short: float | None  # 63d return (decimal)
    ret_long: float | None  # 126d return (decimal)

    @property
    def pullback_low(self) -> float:
        return min(self.lows_recent)


@dataclass(frozen=True)
class TradePlan:
    entry_ref: float
    stop: float
    risk_per_share: float
    stop_atr_multiple: float
    target_2r: float
    chase_limit: float
    invalidation: float
    shares: int
    risk_dollars: float
    position_dollars: float
    regime_blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_ref": round(self.entry_ref, 4),
            "stop": round(self.stop, 4),
            "risk_per_share": round(self.risk_per_share, 4),
            "stop_atr_multiple": round(self.stop_atr_multiple, 4),
            "target_2r": round(self.target_2r, 4),
            "chase_limit": round(self.chase_limit, 4),
            "invalidation": round(self.invalidation, 4),
            "shares": int(self.shares),
            "risk_dollars": round(self.risk_dollars, 2),
            "position_dollars": round(self.position_dollars, 2),
            "regime_blocked": bool(self.regime_blocked),
        }


@dataclass
class TickerOutcome:
    """Mutable while the runner walks the rules / portfolio gates; report.py serialises it."""

    ticker: str
    tier: str
    reason: str | None = None
    checks: list[RuleResult] = field(default_factory=list)
    indicators: SwingIndicators | None = None
    rs_score_pct: float | None = None
    rs_rank: int | None = None
    plan: TradePlan | None = None
    regime_blocked: bool = False
    error: str | None = None
