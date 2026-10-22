"""Postgres persistence for sector-ETF swing paper positions and their fills (Phase 2)."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from quant_hub.infrastructure.postgres.connection import get_connection

logger = logging.getLogger(__name__)

_POSITION_COLUMNS = (
    "id",
    "ticker",
    "status",
    "source_run_id",
    "entry_date",
    "entry_price",
    "initial_shares",
    "open_shares",
    "initial_stop",
    "target_price",
    "trail_mode",
    "max_hold_days",
    "current_stop",
    "trail_level",
    "target_reached",
    "highest_close",
    "last_close",
    "last_bar_date",
    "bars_held",
    "exit_signal",
    "exit_signal_date",
    "exit_signal_detail",
    "closed_date",
    "notes",
    "created_at",
    "updated_at",
)
_FILL_COLUMNS = ("id", "position_id", "side", "fill_date", "price", "shares", "reason", "created_at")

# Realized P&L per position = sum over sells of (sell price - entry price) x shares.
_REALIZED_SQL = """
    COALESCE((
        SELECT SUM((f.price - p.entry_price) * f.shares)
        FROM sector_swing_fills f
        WHERE f.position_id = p.id AND f.side = 'sell'
    ), 0)
"""

_TRACKING_FIELDS = (
    "last_bar_date",
    "last_close",
    "bars_held",
    "highest_close",
    "current_stop",
    "trail_level",
    "target_reached",
    "exit_signal",
    "exit_signal_date",
    "exit_signal_detail",
)


class PositionError(ValueError):
    """A fill or position change that would leave the book inconsistent."""


class SectorSwingPositionsRepository:
    def insert_position(
        self,
        *,
        ticker: str,
        entry_date: date,
        entry_price: float,
        shares: int,
        initial_stop: float,
        target_price: float,
        trail_mode: str,
        max_hold_days: int,
        source_run_id: int | None = None,
        notes: str | None = None,
    ) -> int:
        """Open a position and record its buy fill in one transaction."""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM sector_swing_positions WHERE ticker = %s AND status = 'open'",
                    (ticker,),
                )
                existing = cur.fetchone()
                if existing:
                    raise PositionError(f"{ticker} already has an open position (id {existing[0]})")
                cur.execute(
                    """
                    INSERT INTO sector_swing_positions (
                        ticker, source_run_id, entry_date, entry_price,
                        initial_shares, open_shares, initial_stop, target_price,
                        trail_mode, max_hold_days, current_stop, notes
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        ticker,
                        source_run_id,
                        entry_date,
                        entry_price,
                        shares,
                        shares,
                        initial_stop,
                        target_price,
                        trail_mode,
                        max_hold_days,
                        initial_stop,
                        notes,
                    ),
                )
                position_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO sector_swing_fills (position_id, side, fill_date, price, shares, reason)
                    VALUES (%s, 'buy', %s, %s, %s, 'entry')
                    """,
                    (position_id, entry_date, entry_price, shares),
                )
            conn.commit()
        logger.info("Opened sector swing position id=%s %s x%s @ %s",
                    position_id, ticker, shares, entry_price)
        return position_id

    def record_sell(
        self,
        position_id: int,
        *,
        fill_date: date,
        price: float,
        shares: int,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Record a sell fill; closes the position when no shares remain. Returns the row."""
        if shares <= 0 or price <= 0:
            raise PositionError("Sell price and shares must be positive")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status, open_shares, entry_date FROM sector_swing_positions
                    WHERE id = %s FOR UPDATE
                    """,
                    (position_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise PositionError(f"No position with id {position_id}")
                status, open_shares, entry_date = row
                if status != "open":
                    raise PositionError(f"Position {position_id} is already closed")
                if shares > open_shares:
                    raise PositionError(
                        f"Cannot sell {shares} shares; position {position_id} holds {open_shares}"
                    )
                if fill_date < entry_date:
                    raise PositionError(f"Sell date {fill_date} is before entry date {entry_date}")
                remaining = open_shares - shares
                cur.execute(
                    """
                    INSERT INTO sector_swing_fills (position_id, side, fill_date, price, shares, reason)
                    VALUES (%s, 'sell', %s, %s, %s, %s)
                    """,
                    (position_id, fill_date, price, shares, reason),
                )
                # A logged sell answers the current exit signal; the next refresh recomputes it.
                cur.execute(
                    """
                    UPDATE sector_swing_positions SET
                        open_shares = %s,
                        status = CASE WHEN %s = 0 THEN 'closed' ELSE status END,
                        closed_date = CASE WHEN %s = 0 THEN %s ELSE closed_date END,
                        exit_signal = NULL, exit_signal_date = NULL, exit_signal_detail = NULL,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (remaining, remaining, remaining, fill_date, position_id),
                )
            conn.commit()
        logger.info("Sell fill position=%s x%s @ %s (%s remaining)",
                    position_id, shares, price, remaining)
        position = self.get_position(position_id)
        assert position is not None
        return position

    def update_tracking(self, position_id: int, tracking: dict[str, Any]) -> None:
        """Write the daily job's derived columns (see ``PositionStatus.to_row``)."""
        unknown = set(tracking) - set(_TRACKING_FIELDS)
        if unknown:
            raise ValueError(f"Not tracking columns: {sorted(unknown)}")
        assignments = ", ".join(f"{field} = %s" for field in tracking)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE sector_swing_positions SET {assignments}, updated_at = NOW()
                    WHERE id = %s AND status = 'open'
                    """,
                    [*tracking.values(), position_id],
                )
            conn.commit()

    def delete_position(self, position_id: int) -> bool:
        """Remove a position logged by mistake (its fills cascade)."""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM sector_swing_positions WHERE id = %s", (position_id,))
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted

    def get_position(self, position_id: int) -> dict[str, Any] | None:
        rows = self._select("WHERE p.id = %s", [position_id])
        return rows[0] if rows else None

    def get_open_by_ticker(self, ticker: str) -> dict[str, Any] | None:
        rows = self._select("WHERE p.ticker = %s AND p.status = 'open'", [ticker])
        return rows[0] if rows else None

    def list_positions(self, *, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        where, params = ("WHERE p.status = %s", [status]) if status else ("", [])
        return self._select(
            f"{where} ORDER BY p.status DESC, p.entry_date DESC, p.id DESC LIMIT %s",
            [*params, limit],
        )

    def list_fills(self, position_id: int) -> list[dict[str, Any]]:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT {", ".join(_FILL_COLUMNS)} FROM sector_swing_fills
                    WHERE position_id = %s ORDER BY fill_date, id
                    """,
                    (position_id,),
                )
                return [_clean(dict(zip(_FILL_COLUMNS, row, strict=True)))
                        for row in cur.fetchall()]

    def realized_pnl_between(self, start: date, end: date) -> float:
        """Realized P&L of sell fills dated in [start, end] (the weekly loss-limit input)."""
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM((f.price - p.entry_price) * f.shares), 0)
                    FROM sector_swing_fills f
                    JOIN sector_swing_positions p ON p.id = f.position_id
                    WHERE f.side = 'sell' AND f.fill_date BETWEEN %s AND %s
                    """,
                    (start, end),
                )
                return float(cur.fetchone()[0])

    def _select(self, tail: str, params: list[Any]) -> list[dict[str, Any]]:
        cols = ", ".join(f"p.{c}" for c in _POSITION_COLUMNS)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {cols}, {_REALIZED_SQL} AS realized_pnl "
                    f"FROM sector_swing_positions p {tail}",
                    params,
                )
                rows = []
                for row in cur.fetchall():
                    data = dict(zip((*_POSITION_COLUMNS, "realized_pnl"), row, strict=True))
                    data["realized_pnl"] = float(data["realized_pnl"])
                    rows.append(_clean(data))
                return rows


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
    return data
