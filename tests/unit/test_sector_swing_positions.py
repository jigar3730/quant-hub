"""Phase 2: exit-signal replay (R8), weekly loss flag, and open-position scan gates."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pandas as pd
import pytest
from swing_fixtures import TAIL_TRIGGER, etf, make_frame, path, scenario

from quant_hub.sector_swing import config as C
from quant_hub.sector_swing import runner as runner_mod
from quant_hub.sector_swing.models import TickerOutcome, TradePlan
from quant_hub.sector_swing.positions import (
    SIGNAL_STOP_HIT,
    SIGNAL_TARGET_REACHED,
    SIGNAL_TIME_STOP,
    SIGNAL_TRAIL_EXIT,
    PortfolioState,
    Position,
    evaluate_position,
    target_price,
    trading_paused,
    week_start,
)
from quant_hub.sector_swing.report import build_report, render_markdown
from quant_hub.sector_swing.runner import scan_prices

P = C.DEFAULT_PARAMS
WARM = 60  # flat bars at 100 before the entry bar (EMA/ATR warm-up)


def bars(*tail: float) -> pd.DataFrame:
    """60 flat bars at 100, then ``tail`` closes; the entry is the first tail bar."""
    return make_frame("XLK", [100.0] * WARM + list(tail))


def entry_date(df: pd.DataFrame) -> date:
    return pd.Timestamp(df["Date"].iloc[WARM]).date()


def bar_date(df: pd.DataFrame, n: int) -> date:
    """Date of the n-th bar since entry (1-based)."""
    return pd.Timestamp(df["Date"].iloc[WARM + n - 1]).date()


def position(df: pd.DataFrame, **kw) -> Position:
    base = dict(
        id=1, ticker="XLK", entry_date=entry_date(df), entry_price=100.0,
        initial_shares=100, open_shares=100, initial_stop=98.0,
        target_price=target_price(100.0, 98.0, P), trail_mode="ema10", max_hold_days=10,
    )
    base.update(kw)
    return Position(**base)


# ---------- exit-signal replay ----------


def test_target_is_entry_plus_two_r_from_the_actual_fill():
    assert target_price(100.0, 98.0, P) == pytest.approx(104.0)


def test_no_bars_since_entry_yet():
    df = bars(100.0)
    status = evaluate_position(position(df, entry_date=date(2099, 1, 1)), df, P)
    assert status.bars_held == 0 and status.exit_signal is None
    assert status.last_close is None and status.current_stop == 98.0


def test_stop_hit_on_the_bar_whose_low_trades_the_stop():
    df = bars(100.5, 99.0, 97.5, 101.0)
    status = evaluate_position(position(df), df, P)
    assert status.exit_signal == SIGNAL_STOP_HIT
    assert status.exit_signal_date == bar_date(df, 3)
    assert status.bars_held == 4 and status.last_close == pytest.approx(101.0)


def test_target_reached_asks_to_sell_half_until_shares_are_sold():
    df = bars(101.0, 102.5, 104.5)
    full = evaluate_position(position(df), df, P)
    assert full.exit_signal == SIGNAL_TARGET_REACHED and full.target_reached
    assert full.exit_signal_date == bar_date(df, 3)

    half = evaluate_position(position(df, open_shares=50), df, P)
    assert half.exit_signal is None and half.target_reached
    assert half.trail_level is not None  # EMA10 trail is now live


def test_ema10_trail_only_applies_after_the_target():
    df = bars(101.0, 102.5, 104.5, 100.0)
    status = evaluate_position(position(df, open_shares=50), df, P)
    assert status.exit_signal == SIGNAL_TRAIL_EXIT
    assert status.exit_signal_date == bar_date(df, 4)

    # The same dip without the target is not a trail exit (only the initial stop applies).
    df2 = bars(101.0, 102.5, 103.0, 100.0)
    assert evaluate_position(position(df2), df2, P).exit_signal is None


def test_chandelier_ratchets_the_stop_and_then_gets_hit():
    df = bars(101.0, 102.5, 104.5, 106.0, 101.0)
    status = evaluate_position(position(df, open_shares=50, trail_mode="chandelier"), df, P)
    assert status.exit_signal == SIGNAL_TRAIL_EXIT
    assert status.exit_signal_date == bar_date(df, 5)
    assert status.current_stop > 98.0 and status.highest_close == pytest.approx(106.0)


def test_time_stop_after_max_hold_without_plus_one_r():
    df = bars(*[100.2] * 10)
    status = evaluate_position(position(df), df, P)
    assert status.exit_signal == SIGNAL_TIME_STOP
    assert status.exit_signal_date == bar_date(df, 10)

    df9 = bars(*[100.2] * 9)
    assert evaluate_position(position(df9), df9, P).exit_signal is None


def test_reaching_plus_one_r_on_a_close_cancels_the_time_stop():
    df = bars(102.2, *[100.5] * 12)
    assert evaluate_position(position(df), df, P).exit_signal is None


def test_replay_is_stateless_and_idempotent():
    df = bars(101.0, 102.5, 104.5, 106.0, 101.0)
    pos = position(df, trail_mode="chandelier")
    assert evaluate_position(pos, df, P) == evaluate_position(pos, df, P)


def test_invalid_positions_raise():
    df = bars(100.0)
    with pytest.raises(ValueError):
        evaluate_position(position(df, initial_stop=100.0), df, P)
    with pytest.raises(ValueError):
        evaluate_position(position(df, trail_mode="nope"), df, P)


def test_from_row_accepts_iso_dates():
    row = dict(id=3, ticker="XLE", entry_date="2026-10-20", entry_price=90, initial_shares=10,
               open_shares=10, initial_stop=88, target_price=94, trail_mode="ema10",
               max_hold_days=10)
    assert Position.from_row(row).entry_date == date(2026, 10, 20)


# ---------- weekly loss limit ----------


def test_week_starts_monday():
    assert week_start(date(2026, 10, 22)) == date(2026, 10, 19)  # Thursday -> Monday
    assert week_start(date(2026, 10, 19)) == date(2026, 10, 19)


def test_trading_paused_at_exactly_the_limit():
    assert trading_paused(-1500.0, 50_000, P)  # 3% of 50k
    assert not trading_paused(-1499.99, 50_000, P)
    assert not trading_paused(250.0, 50_000, P)


# ---------- open-position gates in the scan ----------


def _walk(ticker, seed):
    return make_frame(ticker, path(50, 0.0, seed=seed, sigma=0.01))


def _outcome(ticker, rank):
    plan = TradePlan(100, 95, 5, 2, 110, 101, 95, 50, 250, 5000)
    return TickerOutcome(ticker, C.TIER_FILTERED, rs_rank=rank, plan=plan)


def test_already_open_ticker_gets_no_new_plan():
    frames = {t: _walk(t, s) for t, s in (("A", 1), ("B", 2))}
    cands = [_outcome("A", 1), _outcome("B", 2)]
    runner_mod._apply_portfolio_gates(cands, frames, P, {"A": frames["A"]})
    assert cands[0].tier == C.TIER_FILTERED and cands[0].reason == C.REASON_ALREADY_OPEN
    assert cands[0].plan is None
    assert cands[1].tier == C.TIER_TRIGGER


def test_open_positions_use_up_new_signal_slots():
    frames = {t: _walk(t, s) for t, s in zip("ABCD", (1, 2, 3, 4), strict=True)}
    held = {"X": _walk("X", 7), "Y": _walk("Y", 8)}  # 2 of 3 slots taken
    cands = [_outcome(t, i + 1) for i, t in enumerate("ABC")]
    runner_mod._apply_portfolio_gates(cands, frames, P, held)
    assert [c.tier for c in cands] == [C.TIER_TRIGGER, C.TIER_FILTERED, C.TIER_FILTERED]
    assert {c.reason for c in cands[1:]} == {C.REASON_POSITION_LIMIT}
    assert any(r.rule == "P_position_limit" for r in cands[1].checks)


def test_full_book_blocks_every_candidate():
    frames = {"A": _walk("A", 1)}
    held = {"X": None, "Y": None, "Z": None}  # no prices: still count toward the limit
    cands = [_outcome("A", 1)]
    runner_mod._apply_portfolio_gates(cands, frames, P, held)
    assert cands[0].reason == C.REASON_POSITION_LIMIT


def test_signal_cap_still_applies_with_free_slots():
    frames = {t: _walk(t, s) for t, s in zip("ABCD", (1, 2, 3, 4), strict=True)}
    params = replace(P, max_open_positions=10)
    cands = [_outcome(t, i + 1) for i, t in enumerate("ABCD")]
    runner_mod._apply_portfolio_gates(cands, frames, params, {})
    assert cands[3].reason == C.REASON_SIGNAL_CAP


def test_correlation_gate_includes_open_positions_outside_the_universe():
    a = path(50, 0.0, seed=11, sigma=0.01)
    twin = list(np.asarray(a) * (1 + np.random.default_rng(5).normal(0, 0.0004, len(a))))
    frames = {"A": make_frame("A", a)}
    cands = [_outcome("A", 1)]
    runner_mod._apply_portfolio_gates(cands, frames, P, {"HELD": make_frame("HELD", twin)})
    assert cands[0].reason == C.REASON_CORRELATED
    check = next(r for r in cands[0].checks if r.rule == "P_correlation")
    assert "HELD (open)" in check.threshold


def test_scan_end_to_end_with_portfolio_and_paused_flag():
    wide = replace(P, top_n_leaders=16)
    prices = pd.concat([scenario(TRIG=TAIL_TRIGGER), etf("HELD", TAIL_TRIGGER)],
                       ignore_index=True)
    portfolio = PortfolioState(open_tickers=("HELD",), week_start=date(2026, 9, 14),
                               week_realized_pnl=-2_000.0)
    result = scan_prices(prices, ["TRIG"], params=wide, equity=50_000, risk_pct=0.01,
                         portfolio=portfolio)
    trig = result.outcomes[0]
    assert trig.tier == C.TIER_FILTERED and trig.reason == C.REASON_CORRELATED

    report = build_report(
        result, universe=["TRIG"], universe_id="sector_etfs", params=wide, equity=50_000,
        risk_pct=0.01, data_freshness="fresh", expected_session=None,
        scan_date=date(2026, 9, 18), price_cache="parquet", dry_run=False,
    )
    block = report["market_regime"]["portfolio"]
    assert block["open_tickers"] == ["HELD"] and block["trading_paused"] is True
    assert block["weekly_loss_limit"] == pytest.approx(1500.0)
    assert "TRADING PAUSED" in render_markdown(report)


def test_scan_without_portfolio_has_no_portfolio_block():
    result = scan_prices(scenario(TRIG=TAIL_TRIGGER), ["TRIG"],
                         params=replace(P, top_n_leaders=16), equity=50_000, risk_pct=0.01)
    assert result.outcomes[0].tier == C.TIER_TRIGGER and result.portfolio is None
