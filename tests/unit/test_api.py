"""Unit tests for the read-only API (Phase 1) using fake repositories.

No live Postgres required — dependency_overrides swaps in in-memory fakes,
the same approach as tests/unit/test_ml_export_service.py.
"""

from __future__ import annotations

import importlib.util
from datetime import date

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("httpx2") is None,
    reason="fastapi/httpx2 not installed (pip install -e '.[api]')",
)


def _make_client(*, scans=None, outcomes=None, models=None):
    from fastapi.testclient import TestClient

    from quant_hub.api.app import create_app
    from quant_hub.api.deps import get_models_repo, get_outcomes_repo, get_scan_repo

    app = create_app()
    if scans is not None:
        app.dependency_overrides[get_scan_repo] = lambda: scans
    if outcomes is not None:
        app.dependency_overrides[get_outcomes_repo] = lambda: outcomes
    if models is not None:
        app.dependency_overrides[get_models_repo] = lambda: models
    return TestClient(app)


class _FakeScanRepo:
    def __init__(self, runs: dict[int, dict], reports: dict[int, dict]) -> None:
        self._runs = runs
        self._reports = reports

    def list_runs_filtered(self, **_kwargs) -> list[dict]:
        return list(self._runs.values())

    def get_latest_run(self, **_kwargs) -> dict | None:
        return next(iter(self._runs.values()), None)

    def get_report_for_run(self, run_id: int) -> dict | None:
        return self._reports.get(run_id)

    def ticker_history(self, ticker: str, **_kwargs) -> list[dict]:
        return [
            {
                "run_id": 1,
                "scan_date": "2026-06-01",
                "strategy_id": "launchpad",
                "universe_id": "sp500_index",
                "ticker": ticker.upper(),
            }
        ]

    def ticker_history_count(self, ticker: str, **_kwargs) -> int:
        return 1


def _run() -> dict:
    return {
        "id": 1,
        "scan_date": date(2026, 6, 1),
        "scan_time": None,
        "strategy_id": "launchpad",
        "universe_id": "sp500_index",
        "universe_size": 100,
        "tier1_count": 2,
        "tier2_count": 3,
        "tier3_count": 0,
        "filtered_count": 95,
        "actionable_count": 5,
        "regime_label": "neutral",
        "regime_multiplier": 1.0,
    }


def _report() -> dict:
    return {
        "strategy_id": "launchpad",
        "universe_id": "sp500_index",
        "scan_date": "2026-06-01",
        "scan_time": None,
        "scan_summary": {},
        "market_regime": {},
        "tickers": [{"ticker": "AAPL", "eligible": True, "tier": "Tier 1", "final_score": 80.0}],
    }


def test_healthz_reports_status():
    client = _make_client()
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] in {"ok", "degraded"}


def test_scans_list_and_latest():
    repo = _FakeScanRepo({1: _run()}, {1: _report()})
    client = _make_client(scans=repo)

    resp = client.get("/scans")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = client.get("/scans/latest")
    assert resp.status_code == 200
    assert resp.json()["id"] == 1


def test_scan_report_404_for_missing_run():
    repo = _FakeScanRepo({}, {})
    client = _make_client(scans=repo)
    resp = client.get("/scans/999/report")
    assert resp.status_code == 404


def test_scan_report_found():
    repo = _FakeScanRepo({1: _run()}, {1: _report()})
    client = _make_client(scans=repo)
    resp = client.get("/scans/1/report")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tickers"][0]["ticker"] == "AAPL"


def test_ticker_history():
    repo = _FakeScanRepo({}, {})
    client = _make_client(scans=repo)
    resp = client.get("/tickers/aapl/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL"
    assert body["total"] == 1
    assert len(body["rows"]) == 1


class _FakeOutcomesRepo:
    def count_by_status(self) -> dict[str, int]:
        return {"ok": 10, "no_price": 2}

    def list_outcomes_for_run(self, run_id: int, *, horizon_days=None) -> list[dict]:
        return [
            {
                "run_id": run_id,
                "ticker": "AAPL",
                "horizon_days": horizon_days or 10,
                "anchor_date": None,
                "forward_return_pct": 3.5,
                "forward_max_gain_pct": None,
                "forward_max_drawdown_pct": None,
                "spy_forward_return_pct": None,
                "excess_return_pct": None,
                "label_binary": True,
                "label_status": "ok",
                "computed_at": None,
            }
        ]


def test_outcomes_status_and_list():
    client = _make_client(outcomes=_FakeOutcomesRepo())
    resp = client.get("/outcomes/status")
    assert resp.status_code == 200
    assert resp.json() == {"ok": 10, "no_price": 2}

    resp = client.get("/outcomes", params={"run_id": 1})
    assert resp.status_code == 200
    assert resp.json()[0]["ticker"] == "AAPL"


def test_outcomes_requires_run_id():
    client = _make_client(outcomes=_FakeOutcomesRepo())
    resp = client.get("/outcomes")
    assert resp.status_code == 422


class _FakeModelsRepo:
    def list_models(self, **_kwargs) -> list[dict]:
        return [
            {
                "id": 1,
                "name": "launchpad_lgbm_v1",
                "strategy_id": "launchpad",
                "universe_id": "sp500_index",
                "horizon_days": 10,
                "status": "evaluated",
            }
        ]


def test_list_models():
    client = _make_client(models=_FakeModelsRepo())
    resp = client.get("/models")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "launchpad_lgbm_v1"
