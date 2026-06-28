from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from quant_hub.engine.context import ScanContext
    from quant_hub.engine.types import FactorResult, FilterResult, TickerResult
    from quant_hub.regime.market import MarketRegime


class Filter(Protocol):
    name: str

    def evaluate(self, ctx: ScanContext, ticker: str) -> FilterResult: ...


class UniverseFactor(Protocol):
    name: str
    pass_kind: Literal["universe"]

    def compute_universe(
        self,
        ctx: ScanContext,
        tickers: list[str],
    ) -> dict[str, FactorResult]: ...


class TickerFactor(Protocol):
    name: str
    pass_kind: Literal["ticker"]

    def compute(self, ctx: ScanContext, ticker: str) -> FactorResult: ...


Factor = UniverseFactor | TickerFactor


class Penalty(Protocol):
    name: str

    def apply(self, ctx: ScanContext, ticker: TickerResult) -> float: ...


class PortfolioPolicy(Protocol):
    """Stub for future portfolio sizing / ranking layer."""

    def rank(self, scan: Any) -> Any: ...


@dataclass(frozen=True)
class FactorBinding:
    factor: Factor
    column_name: str | None = None

    @property
    def name(self) -> str:
        return self.column_name or self.factor.name


RegimeMode = Literal["multiplier", "factor", "none"]


@dataclass(frozen=True)
class StrategySpec:
    id: str
    name: str
    max_raw_score: float
    filters: list[Filter]
    factor_bindings: list[FactorBinding]
    regime_mode: RegimeMode
    penalties: list[Penalty] = field(default_factory=list)
    sort_keys: list[str] = field(default_factory=lambda: ["final_score"])
    score_columns: list[str] = field(default_factory=list)

    def aggregate(
        self,
        ticker: TickerResult,
        regime: MarketRegime,
    ) -> TickerResult:
        raise NotImplementedError

    def assign_tier(self, ticker: TickerResult) -> str:
        raise NotImplementedError
