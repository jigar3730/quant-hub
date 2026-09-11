"""FastAPI app factory for the read-only Quant Hub API (Phase 1).

Runs beside the Streamlit dashboard, not instead of it — both read the same
Postgres through the same repositories. Nothing here writes to the database
or computes a score; see quant_hub/api/__init__.py for the scope boundary.
"""

from __future__ import annotations

from fastapi import FastAPI

from quant_hub.api.routers import command_center, models, outcomes, scans, tickers
from quant_hub.api.schemas import HealthResponse
from quant_hub.infrastructure.postgres.connection import ping


def create_app() -> FastAPI:
    app = FastAPI(
        title="Quant Hub API",
        description="Read-only API over Launchpad/Lynch scan history (Phase 1, additive).",
        version="0.1.0",
    )

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> dict:
        try:
            db_ok = ping()
        except Exception:
            db_ok = False
        return {"status": "ok" if db_ok else "degraded", "database": db_ok}

    app.include_router(scans.router)
    app.include_router(tickers.router)
    app.include_router(command_center.router)
    app.include_router(outcomes.router)
    app.include_router(models.router)

    return app


app = create_app()
