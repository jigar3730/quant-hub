from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from quant_hub.api.deps import get_scan_repo
from quant_hub.api.schemas import ScanReport, ScanRunSummary
from quant_hub.infrastructure.postgres.repository import ScanRepository

router = APIRouter(prefix="/scans", tags=["scans"])


@router.get("", response_model=list[ScanRunSummary])
def list_scans(
    strategy_id: str | None = None,
    universe_id: str | None = None,
    since: date | None = None,
    until: date | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    repo: ScanRepository = Depends(get_scan_repo),
) -> list[dict]:
    return repo.list_runs_filtered(
        strategy_id=strategy_id,
        universe_id=universe_id,
        since=since,
        until=until,
        limit=limit,
    )


@router.get("/latest", response_model=ScanRunSummary)
def latest_scan(
    strategy_id: str = "launchpad",
    universe_id: str | None = None,
    scan_date: date | None = None,
    repo: ScanRepository = Depends(get_scan_repo),
) -> dict:
    run = repo.get_latest_run(
        strategy_id=strategy_id,
        universe_id=universe_id,
        scan_date=scan_date,
    )
    if run is None:
        raise HTTPException(status_code=404, detail="No matching scan run")
    return run


@router.get("/{run_id}/report", response_model=ScanReport)
def scan_report(run_id: int, repo: ScanRepository = Depends(get_scan_repo)) -> dict:
    report = repo.get_report_for_run(run_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No scan run with id {run_id}")
    return report
