"""Lynch scan history — loaded from Postgres."""

from __future__ import annotations

import logging
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
