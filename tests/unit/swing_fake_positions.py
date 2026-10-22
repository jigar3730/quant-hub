"""In-memory stand-in for SectorSwingPositionsRepository (same method surface, no Postgres)."""

from __future__ import annotations

from datetime import date
from typing import Any

from quant_hub.infrastructure.postgres.sector_swing_positions_repository import PositionError


class FakePositionsRepo:
    def __init__(self) -> None:
        self.positions: dict[int, dict[str, Any]] = {}
        self.fills: list[dict[str, Any]] = []
        self.tracking_calls: list[tuple[int, dict]] = []
        self.week_pnl_calls: list[tuple[date, date]] = []

    def insert_position(self, *, ticker, entry_date, entry_price, shares, initial_stop,
                        target_price, trail_mode, max_hold_days, source_run_id=None,
                        notes=None) -> int:
        if self.get_open_by_ticker(ticker):
            raise PositionError(f"{ticker} already has an open position")
        pid = len(self.positions) + 1
        self.positions[pid] = dict(
            id=pid, ticker=ticker, status="open", source_run_id=source_run_id,
            entry_date=entry_date, entry_price=entry_price, initial_shares=shares,
            open_shares=shares, initial_stop=initial_stop, target_price=target_price,
            trail_mode=trail_mode, max_hold_days=max_hold_days, current_stop=initial_stop,
            trail_level=None, target_reached=False, highest_close=None, last_close=None,
            last_bar_date=None, bars_held=0, exit_signal=None, exit_signal_date=None,
            exit_signal_detail=None, closed_date=None, notes=notes,
        )
        self.fills.append(dict(position_id=pid, side="buy", fill_date=entry_date,
                               price=entry_price, shares=shares, reason="entry"))
        return pid

    def record_sell(self, position_id, *, fill_date, price, shares, reason=None):
        p = self.positions[position_id]
        if shares > p["open_shares"]:
            raise PositionError("oversell")
        self.fills.append(dict(position_id=position_id, side="sell", fill_date=fill_date,
                               price=price, shares=shares, reason=reason))
        p["open_shares"] -= shares
        p["exit_signal"] = None
        if p["open_shares"] == 0:
            p["status"], p["closed_date"] = "closed", fill_date
        return self.get_position(position_id)

    def update_tracking(self, position_id, tracking):
        self.tracking_calls.append((position_id, tracking))
        self.positions[position_id].update(tracking)

    def delete_position(self, position_id):
        return self.positions.pop(position_id, None) is not None

    def _with_pnl(self, p):
        realized = sum((f["price"] - p["entry_price"]) * f["shares"] for f in self.fills
                       if f["position_id"] == p["id"] and f["side"] == "sell")
        return {**p, "realized_pnl": realized}

    def get_position(self, position_id):
        p = self.positions.get(position_id)
        return self._with_pnl(p) if p else None

    def get_open_by_ticker(self, ticker):
        for p in self.positions.values():
            if p["ticker"] == ticker and p["status"] == "open":
                return self._with_pnl(p)
        return None

    def list_positions(self, *, status=None, limit=100):
        rows = [self._with_pnl(p) for p in self.positions.values()
                if status is None or p["status"] == status]
        return rows[:limit]

    def list_fills(self, position_id):
        return [f for f in self.fills if f["position_id"] == position_id]

    def realized_pnl_between(self, start, end):
        self.week_pnl_calls.append((start, end))
        total = 0.0
        for f in self.fills:
            if f["side"] == "sell" and start <= f["fill_date"] <= end:
                total += (f["price"] - self.positions[f["position_id"]]["entry_price"]) * f["shares"]
        return total
