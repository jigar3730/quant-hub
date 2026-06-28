"""Optional DuckDB history for Lynch scans (stub until Lynch strategy ships)."""

from __future__ import annotations

from typing import Any


def get_lynch_ticker_history(ticker: str) -> list[dict[str, Any]]:
    """Return prior Lynch scan rows for *ticker*; empty until Lynch is wired."""
    return []
