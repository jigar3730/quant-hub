"""Sector swing backtest execution model on hand-built bars (no network, no scans)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from quant_hub.sector_swing import backtest as bt

DAYS = pd.bdate_range("2024-01-01", periods=40)


def _prices(bars: dict[str, list[tuple[float, float, float, float]]]) -> pd.DataFrame:
    """bars[ticker] = [(open, high, low, close), ...] on consecutive business days."""
    rows = []
    for ticker, ohlc in bars.items():
        for day, (o, h, low, c) in zip(DAYS, ohlc, strict=False):
            rows.append({"Date": day, "Open": o, "High": h, "Low": low, "Close": c,
                         "Volume": 1e6, "ticker": ticker})
    return pd.DataFrame(rows)


def _flat(n: int, px: float = 100.0) -> list[tuple[float, float, float, float]]:
    return [(px, px, px, px)] * n


def _sig(day: int, ticker: str = "XLK", entry: float = 100.0, stop: float = 95.0,
         chase: float = 102.0, rank: int = 1) -> bt.Signal:
    return bt.Signal(DAYS[day].date(), ticker, rank, entry, stop, chase)


CFG = bt.BacktestConfig(slippage_bps=0.0, initial_equity=100_000.0)


def test_entry_at_next_open_then_stop_out():
    xlk = _flat(1) + [(100, 101, 99, 100), (99, 99, 94, 95)] + _flat(37, 95)
    res = bt.simulate(_prices({"SPY": _flat(40), "XLK": xlk}), [_sig(0)], CFG)

    (trade,) = res.trades
    assert trade.entry_date == DAYS[1].date() and trade.entry_price == 100
    assert trade.exit_reason == "stop" and trade.exit_date == DAYS[2].date()
    assert trade.r_multiple == pytest.approx(-1.0)


def test_gap_below_stop_fills_at_open():
    xlk = _flat(1) + [(100, 100, 100, 100), (90, 91, 89, 90)] + _flat(37, 90)
    (trade,) = bt.simulate(_prices({"SPY": _flat(40), "XLK": xlk}), [_sig(0)], CFG).trades
    assert trade.exit_reason == "stop"
    assert trade.r_multiple == pytest.approx(-2.0)  # (90 - 100) / 5


def test_chase_and_invalidation_skip_entry():
    above_chase = _flat(1) + [(103, 104, 102, 103)] + _flat(38, 103)
    res = bt.simulate(_prices({"SPY": _flat(40), "XLK": above_chase}), [_sig(0)], CFG)
    assert res.trades == [] and res.skipped["chase"] == 1

    below_stop = _flat(1) + [(94, 95, 93, 94)] + _flat(38, 94)
    res = bt.simulate(_prices({"SPY": _flat(40), "XLK": below_stop}), [_sig(0)], CFG)
    assert res.trades == [] and res.skipped["invalidated"] == 1


def test_half_at_target_and_remainder_trailed():
    xlk = (_flat(1) + [(100, 101, 99, 100), (100, 111, 100, 110), (109, 109, 104, 104),
                       (103, 103, 102, 103)] + _flat(35, 103))
    cfg = bt.BacktestConfig(slippage_bps=0.0, params=bt.C.SwingParams(ema_fast=2))
    (trade,) = bt.simulate(_prices({"SPY": _flat(40), "XLK": xlk}), [_sig(0)], cfg).trades
    assert trade.half_taken
    assert trade.exit_reason == "trail" and trade.exit_date == DAYS[4].date()
    # half at 110 (+2R), half at the day-4 open 103 (+0.6R) -> 1.3R
    assert trade.r_multiple == pytest.approx(1.3)


def test_time_stop_when_1r_never_reached():
    xlk = _flat(1) + _flat(39, 101)
    (trade,) = bt.simulate(_prices({"SPY": _flat(40), "XLK": xlk}), [_sig(0)], CFG).trades
    assert trade.exit_reason == "time"
    assert trade.days_held == bt.C.DEFAULT_PARAMS.max_hold_days


def test_capacity_and_one_position_per_ticker():
    bars = {"SPY": _flat(40), "XLK": _flat(40), "XLE": _flat(40), "XLF": _flat(40),
            "XLV": _flat(40)}
    sigs = [_sig(0, t, rank=i) for i, t in enumerate(("XLK", "XLE", "XLF", "XLV"), start=1)]
    sigs.append(_sig(1, "XLK"))
    res = bt.simulate(_prices(bars), sigs, CFG)
    assert {t.ticker for t in res.trades} == {"XLK", "XLE", "XLF"}
    assert res.skipped["capacity"] == 1 and res.skipped["held"] == 1


def test_slippage_applies_both_sides():
    xlk = _flat(1) + [(100, 101, 99, 100), (99, 99, 94, 95)] + _flat(37, 95)
    cfg = bt.BacktestConfig(slippage_bps=10.0)
    (trade,) = bt.simulate(_prices({"SPY": _flat(40), "XLK": xlk}), [_sig(0)], cfg).trades
    assert trade.entry_price == pytest.approx(100.1)
    assert trade.cash_in == pytest.approx(trade.shares * 95 * 0.999)


def test_equity_stats_and_trade_stats():
    eq = pd.Series([100.0, 110.0, 99.0, 121.0], index=pd.bdate_range("2024-01-01", periods=4))
    stats = bt.equity_stats(eq)
    assert stats["total_return_pct"] == pytest.approx(21.0)
    assert stats["max_drawdown_pct"] == pytest.approx(-10.0)

    def trade(r: float) -> bt.Trade:
        t = bt.Trade("X", date(2024, 1, 1), date(2024, 1, 2), 100.0, 95.0, 110.0, 10, 5.0)
        t.cash_in = 1000 + r * 50
        return t

    ts = bt.trade_stats([trade(2), trade(-1), trade(-1), trade(1)])
    assert ts["trades"] == 4 and ts["win_rate"] == 0.5
    assert ts["expectancy_r"] == pytest.approx(0.25)
    assert ts["longest_losing_streak"] == 2
    assert ts["profit_factor"] == pytest.approx(1.5)
