from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from quant_hub.api.deps import get_outcomes_repo
from quant_hub.api.schemas import OutcomeRow
from quant_hub.infrastructure.postgres.outcomes_repository import OutcomesRepository

router = APIRouter(prefix="/outcomes", tags=["outcomes"])


@router.get("/status")
def outcomes_status(repo: OutcomesRepository = Depends(get_outcomes_repo)) -> dict[str, int]:
    return repo.count_by_status()


@router.get("", response_model=list[OutcomeRow])
def list_outcomes(
    run_id: int | None = Query(default=None, description="signal_outcomes.run_id"),
    ticker: str | None = Query(default=None, description="cross-run lookup for one ticker"),
    strategy_id: str | None = None,
    horizon_days: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    repo: OutcomesRepository = Depends(get_outcomes_repo),
) -> list[dict]:
    if run_id is not None:
        return repo.list_outcomes_for_run(run_id, horizon_days=horizon_days)
    if ticker is not None:
        return repo.list_outcomes_for_ticker(
            ticker.upper(),
            strategy_id=strategy_id,
            horizon_days=horizon_days,
            limit=limit,
        )
    raise HTTPException(status_code=422, detail="Provide either run_id or ticker")
