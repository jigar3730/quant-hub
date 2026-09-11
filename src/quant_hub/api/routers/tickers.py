from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from quant_hub.api.deps import get_scan_repo
from quant_hub.api.schemas import TickerHistoryPage
from quant_hub.infrastructure.postgres.repository import ScanRepository

router = APIRouter(prefix="/tickers", tags=["tickers"])


@router.get("/{ticker}/history", response_model=TickerHistoryPage)
def ticker_history(
    ticker: str,
    actionable_only: bool = True,
    strategy_id: str | None = None,
    universe_id: str | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repo: ScanRepository = Depends(get_scan_repo),
) -> dict:
    kwargs = dict(
        actionable_only=actionable_only,
        strategy_id=strategy_id,
        universe_id=universe_id,
        since=since,
        until=until,
    )
    rows = repo.ticker_history(ticker, limit=limit, offset=offset, **kwargs)
    total = repo.ticker_history_count(ticker, **kwargs)
    return {
        "ticker": ticker.upper(),
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": rows,
    }
