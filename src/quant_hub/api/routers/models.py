from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from quant_hub.api.deps import get_models_repo
from quant_hub.api.schemas import ModelSummary
from quant_hub.infrastructure.postgres.ml_models_repository import MlModelsRepository

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelSummary])
def list_models(
    strategy_id: str | None = None,
    universe_id: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    repo: MlModelsRepository = Depends(get_models_repo),
) -> list[dict]:
    """Research model registry — no live inference (docs/ARCHITECTURE_GAPS.md P2)."""
    return repo.list_models(
        strategy_id=strategy_id,
        universe_id=universe_id,
        status=status,
        limit=limit,
    )
