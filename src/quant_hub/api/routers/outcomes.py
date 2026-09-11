from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from quant_hub.api.deps import get_outcomes_repo
from quant_hub.api.schemas import OutcomeRow
from quant_hub.infrastructure.postgres.outcomes_repository import OutcomesRepository

router = APIRouter(prefix="/outcomes", tags=["outcomes"])


@router.get("/status")
def outcomes_status(repo: OutcomesRepository = Depends(get_outcomes_repo)) -> dict[str, int]:
    return repo.count_by_status()


@router.get("", response_model=list[OutcomeRow])
def list_outcomes(
    run_id: int = Query(..., description="signal_outcomes.run_id"),
    horizon_days: int | None = None,
    repo: OutcomesRepository = Depends(get_outcomes_repo),
) -> list[dict]:
    return repo.list_outcomes_for_run(run_id, horizon_days=horizon_days)
