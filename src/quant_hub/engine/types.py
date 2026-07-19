from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from quant_hub.regime.market import MarketRegime


@dataclass(frozen=True)
class FactorResult:
    name: str
    score: float
    max_score: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_score_dict(self) -> dict[str, float | dict]:
        """Legacy report shape: flat score key plus nested detail dict."""
        return {
            "score": self.score,
            "max": self.max_score,
            **self.details,
        }


@dataclass(frozen=True)
class FilterResult:
    passed: bool
    reason: str | None
    checks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TickerResult:
    ticker: str
    eligible: bool
    filter_reason: str | None
    factors: dict[str, FactorResult] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    raw_score: float = 0.0
    normalized_score: float = 0.0
    final_score: float = 0.0
    regime_multiplier: float = 1.0
    tier: str = "filtered"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def penalty_total(self) -> float:
        return sum(self.penalties.values())

    def factor_score(self, name: str) -> float:
        fr = self.factors.get(name)
        return fr.score if fr else 0.0

    def to_row_dict(self) -> dict[str, Any]:
        """Flat dict matching legacy scan CSV columns."""
        row: dict[str, Any] = {
            "ticker": self.ticker,
            "eligible": self.eligible,
            "filter_reason": self.filter_reason or ("eligible" if self.eligible else "unknown"),
            "raw_score": self.raw_score,
            "normalized_score": self.normalized_score,
            "regime_multiplier": self.regime_multiplier,
            "final_adjusted_score": self.final_score,
            "tier": self.tier,
        }
        if "sector_etf" in self.metadata:
            row["sector_etf"] = self.metadata["sector_etf"]
        for name, fr in self.factors.items():
            row[f"{name}_score"] = fr.score
        return row

    def to_legacy_scores_dict(self) -> dict[str, float]:
        """Flat score floats keyed like rs_market_score for report builder."""
        return {f"{name}_score": fr.score for name, fr in self.factors.items()}


@dataclass
class ScanResult:
    strategy_id: str
    universe: list[str]
    regime: MarketRegime
    regime_detail: dict[str, Any]
    tickers: list[TickerResult]
    as_of: datetime = field(default_factory=datetime.now)

    def to_dataframe(self):
        from quant_hub.engine.export import scan_result_to_dataframe

        return scan_result_to_dataframe(self)
