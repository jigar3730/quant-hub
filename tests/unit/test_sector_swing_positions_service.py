"""Phase 2 services and CLI with in-memory repositories (no Postgres, no network)."""

from __future__ import annotations

from datetime import date, datetime
from functools import partial

import pandas as pd
import pytest
from swing_fake_positions import FakePositionsRepo
from swing_fixtures import FakeLoader, make_frame
from test_sector_swing_service import NOW, FakeJobRepo, FakeScanRepo, full_market

from quant_hub.application import sector_swing_service as svc_mod
from quant_hub.application.sector_swing_positions_service import (
    SectorSwingPositionsService,
    realized_r,
)
from quant_hub.application.sector_swing_service import SectorSwingScanService
from quant_hub.cli import sector_swing_positions as cli_mod
from quant_hub.infrastructure.postgres.sector_swing_positions_repository import PositionError
from quant_hub.sector_swing import config as C
from quant_hub.sector_swing.calendar import ET
from quant_hub.sector_swing.runner import SectorSwingRunner

PLAN = {"entry_ref": 60.0, "stop": 57.0, "chase_limit": 60.8, "target_2r": 66.0,
        "regime_blocked": False}


class PlanScanRepo:
    """Latest-scan lookups used when opening a position."""

    def __init__(self, details: list[dict] | None = None, run_id: int | None = 197) -> None:
        self.details = details or []
        self.run_id = run_id

    def get_latest_run(self, **kwargs):
        return {"id": self.run_id} if self.run_id else None

    def list_ticker_details_for_run(self, run_id):
        return self.details


def positions_service(details=None, repo=None, loader=None, run_id=197):
    return SectorSwingPositionsService(
        repo=repo or FakePositionsRepo(),
        scan_repo=PlanScanRepo(details, run_id),
        job_repo=FakeJobRepo(),
        price_loader=loader or FakeLoader(),
    )


# ---------- opening / selling ----------


def test_open_defaults_stop_to_latest_plan_and_rebases_target():
    svc = positions_service([{"ticker": "XLK", "tier": "Tier 1", "trade_plan": PLAN}])
    result = svc.open_position("xlk", price=60.5, shares=100, entry_date=date(2026, 10, 20))
    p = result.position
    assert p["ticker"] == "XLK" and p["initial_stop"] == 57.0 and p["source_run_id"] == 197
    assert p["target_price"] == pytest.approx(60.5 + 2 * 3.5)  # from the fill, not entry_ref
    assert p["trail_mode"] == "ema10" and p["max_hold_days"] == 10
    assert result.warnings == []


def test_open_warns_but_records_when_chasing_or_not_a_trigger():
    svc = positions_service([{"ticker": "XLK", "tier": "Tier 2",
                              "trade_plan": {**PLAN, "regime_blocked": True}}])
    result = svc.open_position("XLK", price=61.0, shares=10)
    assert len(result.warnings) == 2
    assert "regime-blocked" in result.warnings[0] and "chase limit" in result.warnings[1]


def test_open_without_plan_needs_an_explicit_stop():
    svc = positions_service([], run_id=None)
    with pytest.raises(PositionError, match="--stop"):
        svc.open_position("XLE", price=90.0, shares=10)
    result = svc.open_position("XLE", price=90.0, shares=10, stop=87.0)
    assert result.position["source_run_id"] is None and result.warnings


@pytest.mark.parametrize("price,shares,stop", [(57.0, 10, None), (0, 10, None), (60, 0, None),
                                               (60, 10, 61.0)])
def test_open_rejects_bad_inputs(price, shares, stop):
    svc = positions_service([{"ticker": "XLK", "tier": "Tier 1", "trade_plan": PLAN}])
    with pytest.raises(PositionError):
        svc.open_position("XLK", price=price, shares=shares, stop=stop)


def test_open_warns_when_the_book_is_full():
    repo = FakePositionsRepo()
    svc = positions_service(repo=repo)
    for t in ("A", "B", "C"):
        svc.open_position(t, price=10, shares=1, stop=9)
    result = svc.open_position("D", price=10, shares=1, stop=9)
    assert any("already open" in w for w in result.warnings)


def test_sell_half_then_all_by_ticker_closes_with_realized_r():
    svc = positions_service([{"ticker": "XLK", "tier": "Tier 1", "trade_plan": PLAN}])
    svc.open_position("XLK", price=60.0, shares=100, entry_date=date(2026, 10, 20))
    half = svc.sell("XLK", price=66.0, shares=50, fill_date=date(2026, 10, 22))
    assert half["status"] == "open" and half["open_shares"] == 50
    done = svc.sell("1", price=63.0, fill_date=date(2026, 10, 23))
    assert done["status"] == "closed" and done["realized_pnl"] == pytest.approx(450.0)
    assert realized_r(done) == pytest.approx(450.0 / 300.0)
    assert svc.repo.fills[-1]["reason"] == "manual"


def test_sell_reason_defaults_to_the_current_exit_signal():
    svc = positions_service()
    svc.open_position("XLK", price=60.0, shares=10, stop=57.0)
    svc.repo.positions[1]["exit_signal"] = "time_stop"
    svc.sell("XLK", price=60.1)
    assert svc.repo.fills[-1]["reason"] == "time_stop"


def test_resolve_unknown_position():
    with pytest.raises(PositionError):
        positions_service().resolve("ZZZ")


# ---------- refresh ----------


def _position_market() -> pd.DataFrame:
    # XLK flat at 100 then a dip through the 98 stop; SPY just needs a last bar.
    xlk = make_frame("XLK", [100.0] * 60 + [100.5, 97.0], end=pd.Timestamp("2026-09-18"))
    spy = make_frame("SPY", [400.0] * 62, end=pd.Timestamp("2026-09-18"))
    return pd.concat([xlk, spy], ignore_index=True)


def test_refresh_flags_stop_and_writes_tracking():
    repo = FakePositionsRepo()
    svc = positions_service(repo=repo, loader=FakeLoader(_position_market()))
    svc.open_position("XLK", price=100.0, shares=10, stop=98.0, entry_date=date(2026, 9, 17))
    result = svc.refresh(now=datetime(2026, 9, 21, 5, 20, tzinfo=ET))
    assert result.as_of == date(2026, 9, 18) and not result.stale
    assert not result.failed
    assert repo.positions[1]["exit_signal"] == "stop_hit"
    assert svc.job_repo.started[0][0] == C.POSITIONS_JOB_NAME
    assert svc.job_repo.finished[0]["status"] == "success"


def test_refresh_refetches_once_when_the_cache_is_stale():
    fresh = _position_market()
    stale = fresh[pd.to_datetime(fresh["Date"]) < "2026-09-18"]
    loader = FakeLoader(stale, fresh)
    svc = positions_service(loader=loader)
    svc.open_position("XLK", price=100.0, shares=10, stop=98.0, entry_date=date(2026, 9, 17))
    result = svc.refresh(now=datetime(2026, 9, 21, 5, 20, tzinfo=ET))
    assert loader.calls == [True, False]
    assert result.as_of == date(2026, 9, 18) and not result.stale


def test_refresh_isolates_a_position_without_prices():
    repo = FakePositionsRepo()
    svc = positions_service(repo=repo, loader=FakeLoader(_position_market()))
    svc.open_position("XLK", price=100.0, shares=10, stop=98.0, entry_date=date(2026, 9, 17))
    svc.open_position("GONE", price=10.0, shares=10, stop=9.0, entry_date=date(2026, 9, 17))
    result = svc.refresh(now=datetime(2026, 9, 21, 5, 20, tzinfo=ET))
    assert [r["ticker"] for r, _ in result.failed] == ["GONE"]
    assert len(result.updated) == 1


def test_refresh_with_no_open_positions_does_nothing():
    svc = positions_service()
    result = svc.refresh()
    assert result.updated == [] and svc.job_repo.started == []


# ---------- the daily scan reads and refreshes positions ----------


@pytest.fixture
def paths(tmp_path, monkeypatch):
    def fake_paths(strategy_id, universe_id, *, dry_run=False):
        base = tmp_path / ("dry" if dry_run else "live")
        return {"csv": base / "scan_results.csv", "json": base / "report.json",
                "md": base / "summary.md"}

    monkeypatch.setattr(svc_mod, "scan_output_paths", fake_paths)


def scan_service(repo, scan_repo=None):
    return SectorSwingScanService(
        scan_repo=scan_repo or FakeScanRepo(),
        job_repo=FakeJobRepo(),
        runner_factory=partial(SectorSwingRunner, price_loader=FakeLoader(full_market()),
                               now=NOW),
        positions_repo=repo,
    )


def test_daily_scan_gates_on_open_positions_and_refreshes_them(paths):
    repo = FakePositionsRepo()
    repo.insert_position(ticker="XLK", entry_date=date(2026, 9, 16), entry_price=60.0, shares=10,
                         initial_stop=50.0, target_price=80.0, trail_mode="ema10",
                         max_hold_days=10)
    scan_repo = FakeScanRepo()
    scan_service(repo, scan_repo).run(scan_date=date(2026, 9, 21))

    report = scan_repo.calls[0]["report"]
    assert report["scan_summary"]["actionable_count"] == 0  # XLK would trigger, but is held
    xlk = next(t for t in report["tickers"] if t["ticker"] == "XLK")
    assert xlk["eligibility"]["fail_reason"] == C.REASON_ALREADY_OPEN
    assert report["market_regime"]["portfolio"]["open_tickers"] == ["XLK"]
    assert repo.week_pnl_calls == [(date(2026, 9, 21), date(2026, 9, 21))]
    assert [pid for pid, _ in repo.tracking_calls] == [1]
    assert repo.positions[1]["last_bar_date"] == date(2026, 9, 18)


def test_daily_scan_with_no_positions_still_reports_an_empty_book(paths):
    scan_repo = FakeScanRepo()
    scan_service(FakePositionsRepo(), scan_repo).run()
    report = scan_repo.calls[0]["report"]
    assert report["scan_summary"]["actionable_count"] == 1
    assert report["market_regime"]["portfolio"]["open_positions"] == 0


def test_dry_run_never_reads_or_writes_positions(paths):
    repo = FakePositionsRepo()
    repo.insert_position(ticker="XLK", entry_date=date(2026, 9, 16), entry_price=60.0, shares=10,
                         initial_stop=50.0, target_price=80.0, trail_mode="ema10",
                         max_hold_days=10)
    scan_service(repo).run(dry_run=True, persist=False)
    assert repo.week_pnl_calls == [] and repo.tracking_calls == []


# ---------- CLI ----------


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(cli_mod, "setup_logging", lambda *_: None)
    svc = positions_service([{"ticker": "XLK", "tier": "Tier 1", "trade_plan": PLAN}])
    return svc, partial(cli_mod.main, service=svc)


def test_cli_open_sell_list_show(cli, capsys):
    svc, run = cli
    assert run(["open", "XLK", "--price", "60", "--shares", "100", "--date", "2026-10-20"]) == 0
    assert "Opened position 1" in capsys.readouterr().out
    assert run(["sell", "XLK", "--price", "66", "--shares", "50"]) == 0
    assert run(["list"]) == 0
    out = capsys.readouterr().out
    assert "XLK" in out and "50/100" in out
    assert run(["show", "1"]) == 0
    out = capsys.readouterr().out
    assert "buy" in out and "sell" in out


def test_cli_errors_return_2(cli, capsys):
    _, run = cli
    assert run(["sell", "XLE", "--price", "10", "--all"]) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_delete_requires_yes(cli):
    svc, run = cli
    run(["open", "XLK", "--price", "60", "--shares", "10"])
    assert run(["delete", "1"]) == 1 and 1 in svc.repo.positions
    assert run(["delete", "1", "--yes"]) == 0 and 1 not in svc.repo.positions


def test_cli_sell_needs_shares_or_all():
    with pytest.raises(SystemExit):
        cli_mod.build_parser().parse_args(["sell", "XLK", "--price", "1"])
