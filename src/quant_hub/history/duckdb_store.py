"""Cross-scan ticker history — loaded from Postgres."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def get_lynch_ticker_history(ticker: str, *, limit: int = 24) -> list[dict[str, Any]]:
    """Return prior Lynch scan rows for *ticker* from persisted scan runs."""
    try:
        from quant_hub.infrastructure.postgres.connection import ping
        from quant_hub.infrastructure.postgres.repository import ScanRepository

        if not ping():
            return []

        repo = ScanRepository()
        return repo.lynch_ticker_history(ticker, limit=limit)
    except Exception:
        logger.exception("Failed to load Lynch history for %s", ticker)
        return []


def get_ticker_history(
    ticker: str,
    *,
    actionable_only: bool = True,
    strategy_id: str | None = None,
    universe_id: str | None = None,
    since: date | None = None,
    until: date | None = None,
    exclude_fixtures: bool = True,
    limit: int = 500,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return cross-scan history rows for *ticker* (actionable appearances by default)."""
    try:
        from quant_hub.infrastructure.postgres.connection import ping
        from quant_hub.infrastructure.postgres.repository import ScanRepository

        if not ping():
            return []

        repo = ScanRepository()
        return repo.ticker_history(
            ticker,
            actionable_only=actionable_only,
            strategy_id=strategy_id,
            universe_id=universe_id,
            since=since,
            until=until,
            exclude_fixtures=exclude_fixtures,
            limit=limit,
            offset=offset,
        )
    except Exception:
        logger.exception("Failed to load ticker history for %s", ticker)
        return []


def get_ticker_history_count(
    ticker: str,
    *,
    actionable_only: bool = True,
    strategy_id: str | None = None,
    universe_id: str | None = None,
    since: date | None = None,
    until: date | None = None,
    exclude_fixtures: bool = True,
) -> int:
    """Count cross-scan history rows for pagination."""
    try:
        from quant_hub.infrastructure.postgres.connection import ping
        from quant_hub.infrastructure.postgres.repository import ScanRepository

        if not ping():
            return 0

        repo = ScanRepository()
        return repo.ticker_history_count(
            ticker,
            actionable_only=actionable_only,
            strategy_id=strategy_id,
            universe_id=universe_id,
            since=since,
            until=until,
            exclude_fixtures=exclude_fixtures,
        )
    except Exception:
        logger.exception("Failed to count ticker history for %s", ticker)
        return 0
