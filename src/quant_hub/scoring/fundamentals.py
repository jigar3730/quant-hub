from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MetricStatus = Literal["OK", "MISSING", "NOT_APPLICABLE", "CAPPED", "NEGATIVE"]


@dataclass(frozen=True)
class ScoredMetric:
    score: float
    status: MetricStatus
    value: float | None


def score_revenue(growth: float | None, *, status: MetricStatus = "OK") -> ScoredMetric:
    if status in ("MISSING", "NOT_APPLICABLE") or growth is None:
        return ScoredMetric(0.0, status if status != "OK" else "MISSING", None)
    if status == "CAPPED" and growth is not None:
        growth = min(growth, 0.30)
    if growth >= 0.40:
        return ScoredMetric(15.0, status, growth)
    if growth >= 0.25:
        return ScoredMetric(12.0, status, growth)
    if growth >= 0.15:
        return ScoredMetric(8.0, status, growth)
    if growth >= 0.05:
        return ScoredMetric(4.0, status, growth)
    if growth < 0:
        return ScoredMetric(0.0, "NEGATIVE", growth)
    return ScoredMetric(0.0, status, growth)


def score_eps(combined: float | None, *, status: MetricStatus = "OK") -> ScoredMetric:
    if status in ("MISSING", "NOT_APPLICABLE") or combined is None:
        return ScoredMetric(0.0, status if status != "OK" else "MISSING", None)
    if status == "CAPPED" and combined is not None:
        combined = min(combined, 0.30)
    if combined >= 0.50:
        return ScoredMetric(15.0, status, combined)
    if combined >= 0.30:
        return ScoredMetric(12.0, status, combined)
    if combined >= 0.15:
        return ScoredMetric(8.0, status, combined)
    if combined >= 0.0:
        return ScoredMetric(4.0, status, combined)
    return ScoredMetric(0.0, "NEGATIVE", combined)
