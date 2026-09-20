"""Postgres round trip + API for a sector_etf_swing scan (skipped when Postgres is unreachable)."""

from __future__ import annotations

import importlib.util
from datetime import date

import pytest
from swing_fixtures import (
    TAIL_EXTENDED,
    TAIL_TRIGGER,
    TAIL_WATCH,
    bear_spy_closes,
    scenario,
)

from quant_hub.infrastructure.postgres.connection import apply_schema, ping
from quant_hub.infrastructure.postgres.repository import ScanRepository
from quant_hub.sector_swing import config as C
from quant_hub.sector_swing.report import build_report
from quant_hub.sector_swing.runner import scan_prices


def _postgres_available() -> bool:
    try:
        return ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="Postgres not available")

SCAN_DATE = date(2099, 1, 5)  # future-dated => treated as a fixture, cleaned by delete_fixture_runs
UNIVERSE = ["TRIG", "WATCH", "EXT", "GONE"]


@pytest.fixture(scope="module", autouse=True)
def _schema():
    apply_schema()


@pytest.fixture
def repo():
    r = ScanRepository()
    r.delete_fixture_runs()
    yield r
    r.delete_fixture_runs()


def _report(spy=None) -> dict:
    prices = scenario(spy=spy, TRIG=TAIL_TRIGGER, WATCH=TAIL_WATCH, EXT=TAIL_EXTENDED)
    result = scan_prices(prices, UNIVERSE, params=C.DEFAULT_PARAMS, equity=50_000, risk_pct=0.01)
    return build_report(
        result, universe=UNIVERSE, universe_id=C.UNIVERSE_ID, params=C.DEFAULT_PARAMS,
        equity=50_000, risk_pct=0.01, data_freshness=C.FRESHNESS_FRESH,
        expected_session=date(2026, 9, 18), scan_date=SCAN_DATE, price_cache="live",
        dry_run=False,
    )


def _upsert(repo, report) -> int:
    return repo.upsert_scan(
        scan_date=SCAN_DATE, strategy_id=C.STRATEGY_ID, universe_id=C.UNIVERSE_ID, report=report
    )


def test_upsert_round_trip_preserves_tiers_columns_and_payload(repo):
    report = _report()
    tiers = report["scan_summary"]["tier_counts"]
    assert tiers["Tier 1"] == 1  # TRIG (the others are watch / extended / filtered)

    run_id = _upsert(repo, report)
    loaded = repo.load_report(
        strategy_id=C.STRATEGY_ID, universe_id=C.UNIVERSE_ID, scan_date=SCAN_DATE,
        exclude_fixtures=False,
    )

    assert loaded is not None
    s = loaded["scan_summary"]
    assert s["tier_counts"] == tiers
    assert s["actionable_count"] == 1
    assert s["filter_breakdown"] == report["scan_summary"]["filter_breakdown"]
    assert loaded["market_regime"]["regime_gate_passed"] is True
    assert loaded["market_regime"]["as_of_price"] == report["market_regime"]["as_of_price"]

    rows = {t["ticker"]: t for t in loaded["tickers"]}
    assert set(rows) == set(UNIVERSE)
    assert rows["TRIG"]["tier"] == "Tier 1" and rows["TRIG"]["trade_plan"]["shares"] > 0
    assert rows["GONE"]["eligibility"]["fail_reason"] == "no_price_data"

    # Denormalised columns come from the report, not just the JSON blob.
    from quant_hub.infrastructure.postgres.connection import get_connection

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT tier, eligible, sector_etf, final_score, filter_reason FROM ticker_results "
            "WHERE run_id = %s AND ticker = ANY(%s) ORDER BY ticker",
            (run_id, ["TRIG", "GONE"]),
        )
        gone, trig = cur.fetchall()
    assert trig[0] == "Tier 1" and trig[1] is True and trig[2] == "SPY" and trig[3] > 0
    assert gone[0] == "filtered" and gone[1] is False and gone[3] is None
    assert gone[4] == "no_price_data"


def test_rerun_same_day_replaces_rows(repo):
    first = _upsert(repo, _report())
    second = _upsert(repo, _report(spy=bear_spy_closes()))  # regime off -> no Tier 1 this time
    assert first == second  # unique on (scan_date, strategy_id, universe_id)

    loaded = repo.load_report(
        strategy_id=C.STRATEGY_ID, universe_id=C.UNIVERSE_ID, scan_date=SCAN_DATE,
        exclude_fixtures=False,
    )
    assert loaded["scan_summary"]["actionable_count"] == 0
    assert loaded["market_regime"]["regime_gate_passed"] is False
    assert len(loaded["tickers"]) == len(UNIVERSE)
    trig = next(t for t in loaded["tickers"] if t["ticker"] == "TRIG")
    assert trig["tier"] == "Tier 2" and trig["regime_blocked"] is True


def test_ticker_history_does_not_raise_on_sector_swing_rows(repo):
    _upsert(repo, _report())
    kwargs = dict(strategy_id=C.STRATEGY_ID, exclude_fixtures=False)

    rows = repo.ticker_history("TRIG", actionable_only=False, **kwargs)
    assert len(rows) == 1 and rows[0]["strategy_id"] == C.STRATEGY_ID
    assert repo.ticker_history_count("TRIG", actionable_only=False, **kwargs) == 1
    # Sector swing is intentionally invisible to the cross-strategy "actionable" views (Phase 4).
    assert repo.ticker_history("TRIG", actionable_only=True, **kwargs) == []


@pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("httpx2") is None,
    reason="fastapi/httpx2 not installed",
)
def test_api_serves_the_run_with_no_api_changes(repo):
    from fastapi.testclient import TestClient

    from quant_hub.api.app import create_app

    run_id = _upsert(repo, _report())
    client = TestClient(create_app())

    latest = client.get(
        "/scans/latest",
        params={"strategy_id": C.STRATEGY_ID, "universe_id": C.UNIVERSE_ID,
                "scan_date": SCAN_DATE.isoformat()},
    )
    assert latest.status_code == 200
    body = latest.json()
    assert body["id"] == run_id and body["tier1_count"] == 1 and body["actionable_count"] == 1

    full = client.get(f"/scans/{run_id}/report")
    assert full.status_code == 200
    report = full.json()
    assert report["strategy_id"] == C.STRATEGY_ID
    assert report["market_regime"]["regime_gate_passed"] is True
    assert report["market_regime"]["data_freshness"] == "fresh"
    trig = next(t for t in report["tickers"] if t["ticker"] == "TRIG")
    assert trig["tier"] == "Tier 1" and trig["trade_plan"]["invalidation"] < trig["trade_plan"]["entry_ref"]
    assert trig["schema_version"] == 1
