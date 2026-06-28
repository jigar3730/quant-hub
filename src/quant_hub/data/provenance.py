"""Scan data lineage metadata attached to all strategy reports."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any


def build_data_provenance(
    *,
    strategy_id: str,
    universe_id: str,
    scan_date: date | None = None,
    price_source: str = "yfinance",
    price_cache: str = "live",
    fundamentals_cache: str | None = None,
    as_of_price: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Standard lineage block for JSON reports and Postgres metadata."""
    now = datetime.now(timezone.utc)
    block: dict[str, Any] = {
        "scan_date": str(scan_date or date.today()),
        "scan_time_utc": now.isoformat(),
        "universe_id": universe_id,
        "strategy_id": strategy_id,
        "price_source": price_source,
        "price_cache": price_cache,
    }
    if fundamentals_cache is not None:
        block["fundamentals_cache"] = fundamentals_cache
    if as_of_price is not None:
        block["as_of_price"] = as_of_price
    if extra:
        block.update(extra)
    return block
