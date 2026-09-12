"""Unit tests for the MLExportService quality gate and manifest output."""

from __future__ import annotations

import json
from datetime import date

from quant_hub.application.ml_export_service import MLExportService


class _FakeScanRepo:
    def __init__(self, runs: list[dict], details_by_run: dict[int, list[dict]]) -> None:
        self._runs = runs
        self._details_by_run = details_by_run

    def get_run_by_id(self, run_id: int) -> dict | None:
        return next((r for r in self._runs if r["id"] == run_id), None)

    def list_runs_filtered(self, **_kwargs) -> list[dict]:
        return self._runs

    def list_ticker_details_for_run(self, run_id: int) -> list[dict]:
        return self._details_by_run.get(run_id, [])


class _FakeOutcomesRepo:
    def __init__(self, outcome_maps: dict[int, dict[str, dict]]) -> None:
        self._outcome_maps = outcome_maps

    def outcome_map_for_run(self, run_id: int, *, horizon_days: int) -> dict[str, dict]:
        return self._outcome_maps.get(run_id, {})


def _launchpad_run() -> dict:
    return {
        "id": 1,
        "scan_date": date(2026, 6, 1),
        "scan_time": None,
        "strategy_id": "launchpad",
        "universe_id": "sp500_index",
        "universe_size": 100,
        "regime_label": "neutral",
        "regime_multiplier": 1.0,
        "metadata": {},
    }


def _launchpad_detail(ticker: str, *, tier: str = "Tier 1") -> dict:
    return {
        "ticker": ticker,
        "tier": tier,
        "eligible": True,
        "summary": {"final_adjusted_score": 80},
        "scores": {},
    }


def test_quality_gate_drops_bad_tier_and_bad_label_status(tmp_path):
    run = _launchpad_run()
    details = [
        _launchpad_detail("GOOD", tier="Tier 1"),  # ok label -> kept
        _launchpad_detail("FILTERED", tier="Filtered"),  # bad tier -> dropped
        _launchpad_detail("NOPRICE", tier="Tier 2"),  # bad label_status -> dropped
    ]
    outcomes = {
        "GOOD": {"label_status": "ok", "label_binary": True, "horizon_days": 10},
        "NOPRICE": {"label_status": "no_price", "label_binary": None, "horizon_days": 10},
    }
    service = MLExportService(
        scan_repo=_FakeScanRepo([run], {1: details}),
        outcomes_repo=_FakeOutcomesRepo({1: outcomes}),
        output_dir=tmp_path,
    )

    stats = service.run(strategy_id="launchpad", horizon_days=10, quality_gate=True)

    assert stats.rows_raw == 3
    assert stats.rows_written == 1
    assert stats.drop_tier == 1
    assert stats.drop_label_status == 1

    assert len(stats.output_paths) == 1
    manifest_path = stats.output_paths[0].with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["quality_gate"] is True
    assert manifest["row_counts"]["raw"] == 3
    assert manifest["row_counts"]["written"] == 1
    assert manifest["row_counts"]["dropped"]["tier"] == 1
    assert manifest["row_counts"]["dropped"]["label_status"] == 1
    assert manifest["warning"] is None


def test_no_quality_gate_keeps_everything_and_warns_in_manifest(tmp_path):
    run = _launchpad_run()
    details = [
        _launchpad_detail("GOOD", tier="Tier 1"),
        _launchpad_detail("FILTERED", tier="Filtered"),
    ]
    outcomes = {"GOOD": {"label_status": "ok", "label_binary": True, "horizon_days": 10}}
    service = MLExportService(
        scan_repo=_FakeScanRepo([run], {1: details}),
        outcomes_repo=_FakeOutcomesRepo({1: outcomes}),
        output_dir=tmp_path,
    )

    stats = service.run(strategy_id="launchpad", horizon_days=10, quality_gate=False)

    assert stats.rows_written == 2
    assert stats.drop_tier == 0
    manifest_path = stats.output_paths[0].with_suffix(".manifest.json")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["quality_gate"] is False
    assert manifest["warning"] is not None


def test_lynch_export_is_not_gated_on_label_status(tmp_path):
    """Lynch has no signal_outcomes labels; the gate must not drop every row."""
    run = {
        "id": 2,
        "scan_date": date(2026, 6, 1),
        "scan_time": None,
        "strategy_id": "lynch",
        "universe_id": "sp500_index",
        "universe_size": 100,
        "regime_label": "fundamental",
        "regime_multiplier": 1.0,
        "metadata": {},
    }
    details = [
        {
            "ticker": "GOOD",
            "lynch_score": 85,
            "passed": True,
            "metrics": {"data_quality": {"complete": True}},
        },
        {
            "ticker": "BAD",
            "lynch_score": None,
            "passed": False,
            "metrics": {"error": "fetch failed"},
        },
    ]
    service = MLExportService(
        scan_repo=_FakeScanRepo([run], {2: details}),
        outcomes_repo=_FakeOutcomesRepo({}),
        output_dir=tmp_path,
    )

    stats = service.run(strategy_id="lynch", quality_gate=True)

    assert stats.rows_raw == 2
    assert stats.rows_written == 1
    assert stats.drop_fetch_incomplete == 1
