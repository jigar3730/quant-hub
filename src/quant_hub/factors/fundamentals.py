from __future__ import annotations

from dataclasses import dataclass

from quant_hub.engine.context import ScanContext
from quant_hub.factors.base import make_factor_result
from quant_hub.scoring.fundamentals import score_eps, score_revenue


@dataclass
class RevenueFactor:
    name: str = "revenue"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        fund = ctx.fundamentals(ticker)
        scored = score_revenue(
            fund.get("revenue_yoy"),
            status=fund.get("revenue_yoy_status", "MISSING"),
        )
        return make_factor_result(
            self.name,
            scored.score,
            15.0,
            value=scored.value,
            status=scored.status,
            source=fund.get("revenue_yoy_source", ""),
        )


@dataclass
class EpsFactor:
    name: str = "eps"
    pass_kind: str = "ticker"

    def compute(self, ctx: ScanContext, ticker: str):
        fund = ctx.fundamentals(ticker)
        scored = score_eps(
            fund.get("eps_combined"),
            status=fund.get("eps_combined_status", "MISSING"),
        )
        return make_factor_result(
            self.name,
            scored.score,
            15.0,
            value=scored.value,
            status=scored.status,
            source=fund.get("eps_source", ""),
            eps_yoy=fund.get("eps_yoy"),
            eps_cagr_3y=fund.get("eps_cagr_3y"),
        )
