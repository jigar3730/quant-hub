"""SectorSwingPositionsRepository round trip (skipped when Postgres is unreachable)."""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

from quant_hub.infrastructure.postgres.connection import apply_schema, get_connection, ping
from quant_hub.infrastructure.postgres.sector_swing_positions_repository import (
    PositionError,
    SectorSwingPositionsRepository,
)


def _postgres_available() -> bool:
    try:
        return ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="Postgres not available")

PREFIX = "ZZT"  # fixture tickers; real ETF symbols never start with this
D0 = date(2099, 1, 5)  # a Monday


def _cleanup() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sector_swing_positions WHERE ticker LIKE %s", (PREFIX + "%",))
        conn.commit()


@pytest.fixture(scope="module", autouse=True)
def _schema():
    apply_schema()


@pytest.fixture
def repo():
    _cleanup()
    yield SectorSwingPositionsRepository()
    _cleanup()


def _open(repo, ticker=PREFIX + "A", **kw) -> int:
    args = dict(ticker=ticker, entry_date=D0, entry_price=50.0, shares=100, initial_stop=48.0,
                target_price=54.0, trail_mode="ema10", max_hold_days=10, source_run_id=None)
    args.update(kw)
    return repo.insert_position(**args)


def test_open_records_position_and_buy_fill(repo):
    pid = _open(repo, notes="first")
    p = repo.get_position(pid)
    assert p["status"] == "open" and p["open_shares"] == 100 and p["current_stop"] == 48.0
    assert p["entry_date"] == D0 and p["realized_pnl"] == 0.0 and p["notes"] == "first"
    fills = repo.list_fills(pid)
    assert [(f["side"], f["shares"], f["reason"]) for f in fills] == [("buy", 100, "entry")]
    assert repo.get_open_by_ticker(PREFIX + "A")["id"] == pid


def test_one_open_position_per_ticker(repo):
    _open(repo)
    with pytest.raises(PositionError, match="already has an open position"):
        _open(repo)


def test_partial_then_full_sell_closes_and_realizes(repo):
    pid = _open(repo)
    repo.update_tracking(pid, {"exit_signal": "target_reached", "exit_signal_date": D0})
    half = repo.record_sell(pid, fill_date=date(2099, 1, 7), price=54.0, shares=50,
                            reason="target_reached")
    assert half["open_shares"] == 50 and half["status"] == "open"
    assert half["exit_signal"] is None  # a logged sell answers the signal
    done = repo.record_sell(pid, fill_date=date(2099, 1, 9), price=49.0, shares=50)
    assert done["status"] == "closed" and done["closed_date"] == date(2099, 1, 9)
    assert done["realized_pnl"] == pytest.approx(50 * 4.0 - 50 * 1.0)
    # A new position in the same ETF is allowed once the old one is closed.
    assert _open(repo) != pid


def test_sell_guards(repo):
    pid = _open(repo)
    with pytest.raises(PositionError, match="holds 100"):
        repo.record_sell(pid, fill_date=D0, price=50.0, shares=101)
    with pytest.raises(PositionError, match="before entry"):
        repo.record_sell(pid, fill_date=date(2099, 1, 2), price=50.0, shares=1)
    repo.record_sell(pid, fill_date=D0, price=50.0, shares=100)
    with pytest.raises(PositionError, match="already closed"):
        repo.record_sell(pid, fill_date=D0, price=50.0, shares=1)
    with pytest.raises(PositionError, match="No position"):
        repo.record_sell(10**12, fill_date=D0, price=50.0, shares=1)


def test_schema_rejects_entry_at_or_below_stop(repo):
    with pytest.raises(psycopg.errors.CheckViolation):
        _open(repo, initial_stop=50.0)


def test_weekly_realized_pnl_window(repo):
    a = _open(repo, PREFIX + "A")
    b = _open(repo, PREFIX + "B", entry_price=20.0, initial_stop=19.0, target_price=22.0)
    repo.record_sell(a, fill_date=date(2099, 1, 6), price=47.0, shares=100)  # -300 this week
    repo.record_sell(b, fill_date=date(2099, 1, 12), price=21.0, shares=100)  # next week
    assert repo.realized_pnl_between(D0, date(2099, 1, 9)) == pytest.approx(-300.0)
    assert repo.realized_pnl_between(date(2099, 1, 12), date(2099, 1, 16)) == pytest.approx(100.0)


def test_update_tracking_only_known_columns_and_only_open(repo):
    pid = _open(repo)
    repo.update_tracking(pid, {"current_stop": 49.5, "bars_held": 3, "target_reached": True,
                               "last_bar_date": date(2099, 1, 7)})
    p = repo.get_position(pid)
    assert p["current_stop"] == 49.5 and p["bars_held"] == 3 and p["target_reached"] is True
    with pytest.raises(ValueError):
        repo.update_tracking(pid, {"status": "closed"})
    repo.record_sell(pid, fill_date=D0, price=50.0, shares=100)
    repo.update_tracking(pid, {"bars_held": 9})  # closed rows are frozen
    assert repo.get_position(pid)["bars_held"] == 3


def test_list_and_delete_cascades_fills(repo):
    a = _open(repo, PREFIX + "A")
    b = _open(repo, PREFIX + "B")
    repo.record_sell(b, fill_date=D0, price=51.0, shares=100)
    mine = [p for p in repo.list_positions() if p["ticker"].startswith(PREFIX)]
    assert {p["id"] for p in mine} == {a, b}
    assert all(p["ticker"] != PREFIX + "B" for p in repo.list_positions(status="open"))
    assert repo.delete_position(b) is True and repo.list_fills(b) == []
    assert repo.delete_position(b) is False
