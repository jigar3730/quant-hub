"""Pydantic response models for the read-only API.

The outer envelope (run metadata, counts, labels) is stable — it's backed
directly by scan_runs columns — so those fields are typed. The per-ticker
`detail` JSONB varies by strategy (launchpad vs. lynch) and has no schema
version on the row itself yet (docs/MODERNIZATION_AUDIT.md §1.2), so those
stay `extra="allow"` dicts rather than a strict contract this pass would
have to guess at. Tightening that is Phase 2/3 work once the frontend spec
is validated against real payloads (§3.1).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TolerantModel(BaseModel):
    """Base for response shapes mirroring a JSONB payload we don't fully
    control the shape of — unknown/legacy keys are kept, not dropped."""

    model_config = ConfigDict(extra="allow")


class ScanRunSummary(BaseModel):
    id: int
    scan_date: date
    scan_time: datetime | None = None
    strategy_id: str
    universe_id: str
    universe_size: int | None = None
    tier1_count: int | None = None
    tier2_count: int | None = None
    tier3_count: int | None = None
    filtered_count: int | None = None
    actionable_count: int | None = None
    regime_label: str | None = None
    regime_multiplier: float | None = None


class TickerDetail(TolerantModel):
    ticker: str | None = None
    eligible: bool | None = None
    tier: str | None = None
    final_score: float | None = None


class ScanReport(TolerantModel):
    strategy_id: str
    universe_id: str
    scan_date: str
    scan_time: str | None = None
    scan_summary: dict[str, Any]
    market_regime: dict[str, Any]
    tickers: list[TickerDetail]


class TickerHistoryRow(TolerantModel):
    run_id: int
    scan_date: str
    strategy_id: str
    universe_id: str
    ticker: str


class TickerHistoryPage(BaseModel):
    ticker: str
    total: int
    limit: int
    offset: int
    rows: list[TickerHistoryRow]


class OutcomeRow(BaseModel):
    run_id: int
    ticker: str
    horizon_days: int
    anchor_date: date | None = None
    forward_return_pct: float | None = None
    forward_max_gain_pct: float | None = None
    forward_max_drawdown_pct: float | None = None
    spy_forward_return_pct: float | None = None
    excess_return_pct: float | None = None
    label_binary: bool | None = None
    label_status: str
    computed_at: datetime | None = None


class ModelSummary(TolerantModel):
    id: int
    name: str
    strategy_id: str
    universe_id: str
    horizon_days: int | None = None
    status: str | None = None


class HealthResponse(BaseModel):
    status: str
    database: bool
