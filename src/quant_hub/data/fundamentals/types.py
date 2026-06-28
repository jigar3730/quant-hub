from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

MetricStatus = Literal["OK", "MISSING", "NOT_APPLICABLE", "CAPPED", "NEGATIVE"]


@dataclass
class FundamentalsSnapshot:
    ticker: str
    revenue_yoy: float | None = None
    revenue_yoy_status: MetricStatus = "MISSING"
    revenue_yoy_source: str = ""
    eps_combined: float | None = None
    eps_combined_status: MetricStatus = "MISSING"
    eps_yoy: float | None = None
    eps_cagr_3y: float | None = None
    eps_source: str = ""
    quarters_available: int = 0
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fetch_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FundamentalsSnapshot:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})

    @classmethod
    def missing(cls, ticker: str, *, error: str | None = None) -> FundamentalsSnapshot:
        return cls(ticker=ticker.upper(), fetch_error=error)
