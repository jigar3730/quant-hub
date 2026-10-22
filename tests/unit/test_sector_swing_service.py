"""SectorSwingScanService / CLI with fake repositories (no Postgres, no network)."""

from __future__ import annotations

from datetime import datetime
from functools import partial

import pandas as pd
import pytest
from swing_fake_positions import FakePositionsRepo
from swing_fixtures import TAIL_TRIGGER, TAIL_WATCH, FakeLoader, make_frame, path, spy_closes

from quant_hub.application import sector_swing_service as svc_mod
from quant_hub.application.sector_swing_service import SectorSwingScanService
from quant_hub.cli import sector_swing as cli_mod
from quant_hub.sector_swing import config as C
from quant_hub.sector_swing.calendar import ET
from quant_hub.sector_swing.runner import SectorSwingRunner, StaleDataError
from quant_hub.universes.registry import UniverseRegistry

NOW = datetime(2026, 9, 21, 5, 20, tzinfo=ET)


class FakeScanRepo:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def upsert_scan(self, **kwargs) -> int:
        self.calls.append(kwargs)
        return 42


class FakeJobRepo:
    def __init__(self) -> None:
        self.started: list[tuple[str, int]] = []
        self.finished: list[dict] = []

    def start_job(self, name: str, *, tickers_requested: int = 0) -> int:
        self.started.append((name, tickers_requested))
        return 7

    def finish_job(self, job_id: int, **kwargs) -> None:
        self.finished.append({"job_id": job_id, **kwargs})


def universe_tickers() -> list[str]:
    return UniverseRegistry().resolve("sector_etfs")[1]


def full_market(end: str = "2026-09-18") -> pd.DataFrame:
    """SPY plus every ticker in the universe; XLK triggers, XLE is a watch, the rest drift."""
    end_ts = pd.Timestamp(end)
    frames = [make_frame("SPY", spy_closes(), end=end_ts)]
    for name in universe_tickers():
        if name == "XLK":
            closes = path(50, 0.004, tail=TAIL_TRIGGER)
        elif name == "XLE":
            closes = path(50, 0.004, tail=TAIL_WATCH)
        else:
            closes = path(50, 0.0001)
        frames.append(make_frame(name, closes, end=end_ts))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture
def paths(tmp_path, monkeypatch):
    def fake_paths(strategy_id, universe_id, *, dry_run=False):
        base = tmp_path / ("dry" if dry_run else "live") / strategy_id / universe_id
        return {"csv": base / "scan_results.csv", "json": base / "report.json",
                "md": base / "summary.md"}

    monkeypatch.setattr(svc_mod, "scan_output_paths", fake_paths)
    return fake_paths


def make_service(loader, scan_repo=None, job_repo=None, positions_repo=None):
    return SectorSwingScanService(
        scan_repo=scan_repo or FakeScanRepo(),
        job_repo=job_repo or FakeJobRepo(),
        runner_factory=partial(SectorSwingRunner, price_loader=loader, now=NOW),
        positions_repo=positions_repo or FakePositionsRepo(),
    )


def test_run_persists_once_and_audits_job(paths):
    scan_repo, job_repo = FakeScanRepo(), FakeJobRepo()
    service = make_service(FakeLoader(full_market()), scan_repo, job_repo)

    result = service.run(equity=50_000)

    assert result.exit_code() == 0 and not result.dataframe.empty
    assert len(scan_repo.calls) == 1
    call = scan_repo.calls[0]
    assert call["strategy_id"] == "sector_etf_swing" and call["universe_id"] == "sector_etfs"
    assert call["report"]["scan_summary"]["actionable_count"] == 1
    n = len(universe_tickers())
    assert job_repo.started == [("sector-swing-daily", n)]
    assert len(job_repo.finished) == 1
    fin = job_repo.finished[0]
    assert fin["status"] == "success" and fin["tickers_fetched"] == n and fin["tickers_failed"] == 0

    live = paths("sector_etf_swing", "sector_etfs")
    assert live["csv"].exists() and live["json"].exists() and live["md"].exists()


def test_report_choice_limits_exports(paths):
    service = make_service(FakeLoader(full_market()))
    service.run(report="json")
    live = paths("sector_etf_swing", "sector_etfs")
    assert live["json"].exists() and not live["md"].exists()


def test_dry_run_persists_nothing_and_skips_job(paths):
    scan_repo, job_repo = FakeScanRepo(), FakeJobRepo()
    loader = FakeLoader()
    service = make_service(loader, scan_repo, job_repo)

    result = service.run(dry_run=True, persist=False)

    assert result.exit_code() == 0
    assert scan_repo.calls == [] and job_repo.started == [] and job_repo.finished == []
    assert loader.calls == []  # synthetic prices, no network
    assert paths("sector_etf_swing", "sector_etfs", dry_run=True)["json"].exists()


def test_stale_data_fails_job_and_never_persists(paths):
    scan_repo, job_repo = FakeScanRepo(), FakeJobRepo()
    stale = full_market(end="2026-09-16")
    service = make_service(FakeLoader(stale, stale), scan_repo, job_repo)

    with pytest.raises(StaleDataError):
        service.run()

    assert scan_repo.calls == []
    assert job_repo.finished[0]["status"] == "failed"
    assert "Stale price data" in job_repo.finished[0]["error_message"]


def test_persist_false_skips_upsert_but_keeps_job(paths):
    scan_repo, job_repo = FakeScanRepo(), FakeJobRepo()
    make_service(FakeLoader(full_market()), scan_repo, job_repo).run(persist=False)
    assert scan_repo.calls == [] and job_repo.finished[0]["status"] == "success"


def test_upsert_failure_marks_job_failed(paths):
    class Boom(FakeScanRepo):
        def upsert_scan(self, **kwargs):
            raise RuntimeError("db down")

    job_repo = FakeJobRepo()
    service = make_service(FakeLoader(full_market()), Boom(), job_repo)
    with pytest.raises(RuntimeError, match="db down"):
        service.run()
    assert job_repo.finished[0]["status"] == "failed"


# ---- CLI ----
def test_cli_returns_nonzero_on_stale_data(monkeypatch, capsys):
    class FailingService:
        def run(self, **kwargs):
            raise StaleDataError("Stale price data: SPY last bar 2026-09-16")

    monkeypatch.setattr(cli_mod, "SectorSwingScanService", FailingService)
    monkeypatch.setattr(cli_mod, "setup_logging", lambda *_: None)
    assert cli_mod.run_sector_swing() == 1


def test_cli_maps_flags_to_service(monkeypatch):
    seen: dict = {}

    class Recorder:
        def run(self, **kwargs):
            seen.update(kwargs)
            from quant_hub.application.run_result import ServiceRunResult

            return ServiceRunResult(dataframe=pd.DataFrame())

    monkeypatch.setattr(cli_mod, "SectorSwingScanService", Recorder)
    monkeypatch.setattr(cli_mod, "setup_logging", lambda *_: None)

    code = cli_mod.main(["--force-refresh", "--allow-stale", "--equity", "80000",
                         "--risk-pct", "0.005", "--report", "md"])

    assert code == 0
    assert seen["use_cache"] is False and seen["allow_stale"] is True
    assert seen["equity"] == 80_000 and seen["risk_pct"] == 0.005
    assert seen["report"] == "md" and seen["persist"] is True and seen["dry_run"] is False


def test_cli_dry_run_never_persists(monkeypatch):
    seen: dict = {}

    class Recorder:
        def run(self, **kwargs):
            seen.update(kwargs)
            from quant_hub.application.run_result import ServiceRunResult

            return ServiceRunResult(dataframe=pd.DataFrame())

    monkeypatch.setattr(cli_mod, "SectorSwingScanService", Recorder)
    monkeypatch.setattr(cli_mod, "setup_logging", lambda *_: None)
    cli_mod.main(["--dry-run"])
    assert seen["dry_run"] is True and seen["persist"] is False


@pytest.mark.parametrize("argv", [["--risk-pct", "5"], ["--risk-pct", "0"], ["--equity", "-1"]])
def test_cli_rejects_bad_sizing_args(argv):
    with pytest.raises(SystemExit):
        cli_mod.main(argv)


def test_equity_resolution_order(monkeypatch):
    monkeypatch.delenv(C.EQUITY_ENV, raising=False)
    assert C.resolve_equity() == C.DEFAULT_EQUITY
    monkeypatch.setenv(C.EQUITY_ENV, "125000")
    assert C.resolve_equity() == 125_000
    assert C.resolve_equity(10_000) == 10_000  # CLI wins over env
    with pytest.raises(ValueError):
        C.resolve_equity(0)


def test_status_lists_sector_swing_without_widening_argparse_choices():
    from quant_hub.cli import status

    assert status.STRATEGY_CHOICES == ("launchpad", "lynch")  # report/history/show unchanged
    assert status.STATUS_STRATEGIES == ("launchpad", "lynch", "sector_etf_swing")
