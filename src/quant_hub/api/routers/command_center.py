from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends

from quant_hub.api.deps import get_scan_repo
from quant_hub.digest.command_center import build_command_center_payload
from quant_hub.infrastructure.postgres.repository import ScanRepository

router = APIRouter(tags=["command-center"])


@router.get("/command-center")
def command_center(
    scan_date: date | None = None,
    repo: ScanRepository = Depends(get_scan_repo),
) -> dict[str, Any]:
    """Same payload the Command Center dashboard page and digest job use.

    Defaults to today when scan_date is omitted; returns an empty-coverage
    payload (not a 404) when no runs exist for that date, matching the
    dashboard's own behavior for a day with no scans yet.
    """
    return build_command_center_payload(repo, scan_date=scan_date or date.today())
