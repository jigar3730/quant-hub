from __future__ import annotations

from dataclasses import dataclass

from quant_hub.engine.context import ScanContext
from quant_hub.engine.types import FilterResult
from quant_hub.filters.eligibility import check_eligibility, eligibility_detail


@dataclass
class BreakoutEligibilityFilter:
    name: str = "breakout_eligibility"

    def evaluate(self, ctx: ScanContext, ticker: str) -> FilterResult:
        df = ctx.stock_df(ticker)
        if df is None or df.empty:
            return FilterResult(passed=False, reason="no_price_data", checks=[])
        detail = eligibility_detail(df)
        return FilterResult(
            passed=detail["passed"],
            reason=detail["fail_reason"] if not detail["passed"] else "eligible",
            checks=detail.get("checks", []),
        )


def check_breakout_eligibility(df) -> tuple[bool, str]:
    """Backward-compatible wrapper."""
    return check_eligibility(df)
