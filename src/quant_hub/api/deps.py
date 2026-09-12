"""FastAPI dependencies — one shared repository instance per request.

Repositories are stateless wrappers around the process-wide connection pool
(infrastructure/postgres/connection.py), so instantiating one per request is
cheap; these are simple functions (not a DI container) so tests can override
them via `app.dependency_overrides`.
"""

from __future__ import annotations

from quant_hub.infrastructure.postgres.ml_models_repository import MlModelsRepository
from quant_hub.infrastructure.postgres.outcomes_repository import OutcomesRepository
from quant_hub.infrastructure.postgres.repository import ScanRepository


def get_scan_repo() -> ScanRepository:
    return ScanRepository()


def get_outcomes_repo() -> OutcomesRepository:
    return OutcomesRepository()


def get_models_repo() -> MlModelsRepository:
    return MlModelsRepository()
