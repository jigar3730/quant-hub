"""Test/fixture scan runs that must not appear in production dashboards or status."""

from __future__ import annotations

from datetime import date

# Universe ids used only by unit/integration tests or ad-hoc dry runs.
FIXTURE_UNIVERSE_IDS = frozenset({"test-upsert", "custom"})


def is_fixture_universe(universe_id: str | None) -> bool:
    return universe_id in FIXTURE_UNIVERSE_IDS


def is_fixture_scan_date(scan_date: date) -> bool:
    """Future-dated runs are test fixtures (e.g. 2099-01-01 upsert tests)."""
    return scan_date > date.today()
