"""Phase 2 paper-position tracking: pure exit-signal evaluation (R8) and portfolio state.

Nothing here sells anything. ``evaluate_position`` replays every completed bar since the entry
fill and reports the *current advisory action*; the user records the actual fill by hand. The
replay is stateless (recomputed from the entry date each run), so a missed day or a re-run
cannot drift the trailing stop.

Exit rules (spec R8, with the choices it leaves open made explicit):

- **Initial stop**: a bar whose Low <= the stop (stop-order semantics) -> ``stop_hit``.
- **Target** (entry + ``target_r`` x R): a bar whose High >= target (limit-order semantics)
  -> ``target_reached`` ("sell half"), shown only while no shares have been sold yet.
- **Trail** (only after the target, on the remainder):
  ``ema10`` -> a Close below EMA(10) -> ``trail_exit``;
  ``chandelier`` -> the stop ratchets up to highest close since entry - k x ATR, and a later
  bar's Low at/below it -> ``trail_exit``.
- **Time stop**: after ``max_hold_days`` bars (the entry bar counts as 1) with no Close at or
  above entry + 1R -> ``time_stop`` (exit at that close).

R is measured from the actual entry fill to the initial stop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from quant_hub.indicators import atr, ema
from quant_hub.sector_swing.config import SwingParams

SIGNAL_STOP_HIT = "stop_hit"
SIGNAL_TARGET_REACHED = "target_reached"
SIGNAL_TRAIL_EXIT = "trail_exit"
SIGNAL_TIME_STOP = "time_stop"
EXIT_SIGNALS = (SIGNAL_STOP_HIT, SIGNAL_TARGET_REACHED, SIGNAL_TRAIL_EXIT, SIGNAL_TIME_STOP)

SIGNAL_ACTION = {
    SIGNAL_STOP_HIT: "Exit all: stop level traded",
    SIGNAL_TARGET_REACHED: "Sell half: 2R target traded; trail the rest",
    SIGNAL_TRAIL_EXIT: "Exit remainder: trailing exit triggered",
    SIGNAL_TIME_STOP: "Exit all: time stop (no +1R within the hold window)",
}

TRAIL_MODES = ("ema10", "chandelier")


@dataclass(frozen=True)
class Position:
    """The parts of a ``sector_swing_positions`` row the evaluator needs."""

    id: int | None
    ticker: str
    entry_date: date
    entry_price: float
    initial_shares: int
    open_shares: int
    initial_stop: float
    target_price: float
    trail_mode: str
    max_hold_days: int

    @property
    def risk_per_share(self) -> float:
        return self.entry_price - self.initial_stop

    @classmethod
    def from_row(cls, row: dict) -> Position:
        return cls(
            id=row.get("id"),
            ticker=row["ticker"],
            entry_date=_as_date(row["entry_date"]),
            entry_price=float(row["entry_price"]),
            initial_shares=int(row["initial_shares"]),
            open_shares=int(row["open_shares"]),
            initial_stop=float(row["initial_stop"]),
            target_price=float(row["target_price"]),
            trail_mode=row["trail_mode"],
            max_hold_days=int(row["max_hold_days"]),
        )


@dataclass(frozen=True)
class PositionStatus:
    """Tracking columns written back to the position row by the daily job."""

    last_bar_date: date | None
    last_close: float | None
    bars_held: int
    highest_close: float | None
    current_stop: float
    trail_level: float | None
    target_reached: bool
    exit_signal: str | None
    exit_signal_date: date | None
    exit_signal_detail: str | None

    def to_row(self) -> dict:
        return {
            "last_bar_date": self.last_bar_date,
            "last_close": self.last_close,
            "bars_held": self.bars_held,
            "highest_close": self.highest_close,
            "current_stop": self.current_stop,
            "trail_level": self.trail_level,
            "target_reached": self.target_reached,
            "exit_signal": self.exit_signal,
            "exit_signal_date": self.exit_signal_date,
            "exit_signal_detail": self.exit_signal_detail,
        }


@dataclass(frozen=True)
class PortfolioState:
    """Open-position context handed to the scan (spec 5.4, Phase 2 gates)."""

    open_tickers: tuple[str, ...] = ()
    week_start: date | None = None
    week_realized_pnl: float = 0.0

    def to_dict(self, params: SwingParams, equity: float) -> dict:
        limit = params.weekly_loss_limit_pct * equity
        return {
            "open_positions": len(self.open_tickers),
            "open_tickers": list(self.open_tickers),
            "max_open_positions": params.max_open_positions,
            "week_start": str(self.week_start) if self.week_start else None,
            "week_realized_pnl": round(self.week_realized_pnl, 2),
            "weekly_loss_limit": round(limit, 2),
            "trading_paused": trading_paused(self.week_realized_pnl, equity, params),
        }


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def week_start(day: date) -> date:
    """Monday of ``day``'s calendar week (the weekly loss limit resets every Monday)."""
    return day - timedelta(days=day.weekday())


def trading_paused(week_realized_pnl: float, equity: float, params: SwingParams) -> bool:
    """Advisory flag: realized losses this week reached WEEKLY_LOSS_LIMIT_PCT of equity."""
    return week_realized_pnl <= -params.weekly_loss_limit_pct * equity


def target_price(entry_price: float, initial_stop: float, params: SwingParams) -> float:
    return entry_price + params.target_r * (entry_price - initial_stop)


def evaluate_position(pos: Position, df: pd.DataFrame, params: SwingParams) -> PositionStatus:
    """Replay completed bars since ``pos.entry_date``. ``df`` is a sorted ``ticker_df`` frame
    including history before the entry (EMA/ATR warm-up)."""
    if pos.risk_per_share <= 0:
        raise ValueError(f"{pos.ticker}: entry {pos.entry_price} is not above stop {pos.initial_stop}")
    if pos.trail_mode not in TRAIL_MODES:
        raise ValueError(f"{pos.ticker}: unknown trail mode {pos.trail_mode!r}")

    frame = df.reset_index(drop=True)
    dates = pd.to_datetime(frame["Date"]).dt.date
    close = frame["Close"].astype(float)
    ema_fast = ema(close, params.ema_fast)
    atr_series = atr(frame.astype({"High": float, "Low": float, "Close": float}),
                     params.atr_window)
    since = frame.index[dates >= pos.entry_date]

    one_r = pos.entry_price + pos.risk_per_share
    stop = pos.initial_stop
    trail_level: float | None = None
    highest: float | None = None
    target_date: date | None = None
    reached_1r = False
    signal: tuple[str, date, str] | None = None

    for n, i in enumerate(since, start=1):
        bar_date = dates[i]
        low = float(frame.at[i, "Low"])
        high = float(frame.at[i, "High"])
        bar_close = float(close[i])

        if low <= stop:
            kind = SIGNAL_TRAIL_EXIT if stop > pos.initial_stop else SIGNAL_STOP_HIT
            signal = (kind, bar_date, f"Low {low:.2f} <= stop {stop:.2f}")
            break

        highest = bar_close if highest is None else max(highest, bar_close)
        reached_1r = reached_1r or bar_close >= one_r
        if target_date is None and high >= pos.target_price:
            target_date = bar_date

        if target_date is not None:
            if pos.trail_mode == "ema10":
                level = float(ema_fast[i])
                if math.isfinite(level):
                    trail_level = level
                    if bar_close < level:
                        signal = (SIGNAL_TRAIL_EXIT, bar_date,
                                  f"Close {bar_close:.2f} < EMA{params.ema_fast} {level:.2f}")
                        break
            else:
                bar_atr = float(atr_series[i])
                if math.isfinite(bar_atr):
                    trail_level = highest - params.chandelier_atr * bar_atr
                    stop = max(stop, trail_level)
        elif n >= pos.max_hold_days and not reached_1r:
            signal = (SIGNAL_TIME_STOP, bar_date,
                      f"{n} bars held, no close >= +1R ({one_r:.2f})")
            break

    if signal is None and target_date is not None and pos.open_shares == pos.initial_shares:
        signal = (SIGNAL_TARGET_REACHED, target_date,
                  f"High >= target {pos.target_price:.2f}")

    has_bars = len(since) > 0
    return PositionStatus(
        last_bar_date=dates.iloc[-1] if has_bars else None,
        last_close=float(close.iloc[-1]) if has_bars else None,
        bars_held=len(since),
        highest_close=highest,
        current_stop=stop,
        trail_level=trail_level,
        target_reached=target_date is not None,
        exit_signal=signal[0] if signal else None,
        exit_signal_date=signal[1] if signal else None,
        exit_signal_detail=signal[2] if signal else None,
    )
