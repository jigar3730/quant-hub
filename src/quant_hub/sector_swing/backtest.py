"""Sector-ETF swing backtest (spec Phase 3).

Replays the production ``scan_prices`` point-in-time, one session at a time, then simulates the
trade plans with next-session-open fills. Nothing here writes to ``scan_runs``.

Execution model (spec 5.3 / R8; choices the spec leaves open are marked DECISION):
- Signal on the close of day d; the order is for the open of d+1. Skip when the open is above
  the chase limit or at/below the stop. Fill = open x (1 + slippage).
- Position size uses the production sizing (1% equity risk, 30% max position), recomputed from
  the actual fill and the current marked-to-market equity.
- Intrabar order on any day: stop is checked before target (DECISION: conservative when a bar
  spans both). Gaps fill at the open.
- Target 1 = fill + 2R (the plan's risk recomputed from the fill): sell half.
- Trailing exit (EMA10 close rule) applies to the remainder after Target 1, and to the whole
  position once the time-stop window has passed with +1R reached (DECISION: the spec does not
  say what exits a trade that reached +1R but not 2R). A close below EMA10 exits at the next
  open.
- Time stop: at the close of the MAX_HOLD_DAYS-th session if the highest close since entry
  never reached fill + 1R.
- At most ``max_concurrent`` open positions and one position per ticker (DECISION: spec Phase 2
  portfolio limit, applied here so exposure is bounded). The correlation gate is applied only
  within a scan, as in production.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from quant_hub.config import BENCHMARK_TICKER
from quant_hub.indicators import ema, return_over_days
from quant_hub.sector_swing import config as C
from quant_hub.sector_swing.config import SwingParams
from quant_hub.sector_swing.runner import SectorSwingError, scan_prices
from quant_hub.sector_swing.sizing import position_size

logger = logging.getLogger(__name__)

# Live scans download LOOKBACK_DAYS x 1.6 calendar days (~278 sessions); replay the same depth
# so EMA/ADX warm-up matches production.
DEFAULT_WINDOW_BARS = 280


@dataclass(frozen=True)
class BacktestConfig:
    start: date | None = None
    end: date | None = None
    initial_equity: float = 100_000.0
    slippage_bps: float = 2.0
    window_bars: int = DEFAULT_WINDOW_BARS
    max_concurrent: int = 3
    params: SwingParams = C.DEFAULT_PARAMS

    @property
    def slip(self) -> float:
        return self.slippage_bps / 10_000.0


@dataclass(frozen=True)
class Signal:
    signal_date: date
    ticker: str
    rs_rank: int
    entry_ref: float
    stop: float
    chase_limit: float


@dataclass
class Trade:
    ticker: str
    signal_date: date
    entry_date: date
    entry_price: float
    stop: float
    target: float
    shares: int
    risk_per_share: float
    exit_date: date | None = None
    exit_reason: str = ""
    remaining: int = 0
    cash_in: float = 0.0  # proceeds from sells so far
    days_held: int = 0
    max_close: float = 0.0
    half_taken: bool = False
    trailing: bool = False
    exit_next_open: bool = False

    @property
    def cost(self) -> float:
        return self.shares * self.entry_price

    @property
    def pnl(self) -> float:
        return self.cash_in - self.cost

    @property
    def r_multiple(self) -> float:
        risk = self.shares * self.risk_per_share
        return self.pnl / risk if risk > 0 else 0.0

    def to_row(self) -> dict:
        row = {k: v for k, v in asdict(self).items()
               if k not in ("remaining", "exit_next_open", "trailing", "max_close")}
        row.update(pnl=self.pnl, r_multiple=self.r_multiple)
        return row


# --------------------------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------------------------


def _split_by_ticker(prices: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out = {}
    for ticker, df in prices.groupby("ticker", sort=False):
        df = df.copy()
        df["Date"] = pd.to_datetime(df["Date"])
        out[str(ticker)] = df.sort_values("Date").reset_index(drop=True)
    return out


def _scan_dates(frames: dict[str, pd.DataFrame], cfg: BacktestConfig) -> list[date]:
    spy = frames[BENCHMARK_TICKER]["Date"]
    dates = [d.date() for d in spy.iloc[cfg.window_bars - 1:]]
    if cfg.start:
        dates = [d for d in dates if d >= cfg.start]
    if cfg.end:
        dates = [d for d in dates if d <= cfg.end]
    return dates


def _signals_for_dates(
    args: tuple[dict[str, pd.DataFrame], list[str], list[date], BacktestConfig],
) -> list[Signal]:
    frames, universe, dates, cfg = args
    index = {t: df["Date"].to_numpy(dtype="datetime64[ns]") for t, df in frames.items()}
    signals: list[Signal] = []
    for d in dates:
        cutoff = np.datetime64(pd.Timestamp(d))
        parts = []
        for ticker, df in frames.items():
            end = int(np.searchsorted(index[ticker], cutoff, side="right"))
            if end:
                parts.append(df.iloc[max(0, end - cfg.window_bars):end])
        try:
            result = scan_prices(
                pd.concat(parts, ignore_index=True),
                universe,
                params=cfg.params,
                equity=cfg.initial_equity,
                risk_pct=cfg.params.risk_pct,
            )
        except SectorSwingError as exc:
            logger.warning("Scan skipped for %s: %s", d, exc)
            continue
        for o in result.outcomes:
            if o.tier == C.TIER_TRIGGER and o.plan is not None:
                signals.append(Signal(d, o.ticker, int(o.rs_rank or 0), o.plan.entry_ref,
                                      o.plan.stop, o.plan.chase_limit))
    return signals


def generate_signals(
    prices: pd.DataFrame,
    universe: list[str],
    cfg: BacktestConfig,
    *,
    workers: int = 1,
) -> list[Signal]:
    """Run the production scan for every session in range. Parallel over date chunks."""
    frames = _split_by_ticker(prices)
    if BENCHMARK_TICKER not in frames:
        raise SectorSwingError(f"Missing benchmark data for {BENCHMARK_TICKER}")
    dates = _scan_dates(frames, cfg)
    logging.getLogger("quant_hub.sector_swing.runner").setLevel(logging.ERROR)
    if workers <= 1 or len(dates) < 50:
        return _signals_for_dates((frames, universe, dates, cfg))
    chunks = [list(c) for c in np.array_split(np.array(dates, dtype=object), workers * 4) if len(c)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = pool.map(_signals_for_dates, [(frames, universe, c, cfg) for c in chunks])
    return sorted((s for chunk in results for s in chunk), key=lambda s: (s.signal_date, s.rs_rank))


# --------------------------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------------------------


@dataclass
class SimulationResult:
    trades: list[Trade]
    equity: pd.Series  # marked-to-market at each close
    open_count: pd.Series
    skipped: dict[str, int] = field(default_factory=dict)


def simulate(prices: pd.DataFrame, signals: Iterable[Signal], cfg: BacktestConfig) -> SimulationResult:
    params = cfg.params
    frames = {t: df.set_index("Date") for t, df in _split_by_ticker(prices).items()}
    ema10 = {t: ema(df["Close"].astype(float), params.ema_fast) for t, df in frames.items()}
    calendar = frames[BENCHMARK_TICKER].index
    by_date: dict[pd.Timestamp, list[Signal]] = {}
    for s in signals:
        by_date.setdefault(pd.Timestamp(s.signal_date), []).append(s)
    if not by_date:
        empty = pd.Series(dtype=float)
        return SimulationResult([], empty, empty, {})
    calendar = calendar[calendar >= min(by_date)]
    if cfg.end:
        calendar = calendar[calendar <= pd.Timestamp(cfg.end)]

    cash = cfg.initial_equity
    open_trades: list[Trade] = []
    closed: list[Trade] = []
    pending: list[Signal] = []
    equity_points: dict[pd.Timestamp, float] = {}
    open_points: dict[pd.Timestamp, int] = {}
    skipped = {"chase": 0, "invalidated": 0, "capacity": 0, "held": 0, "no_bar": 0, "size": 0}
    last_equity = cfg.initial_equity

    def sell(trade: Trade, qty: int, price: float, day: pd.Timestamp, reason: str) -> None:
        nonlocal cash
        qty = min(qty, trade.remaining)
        proceeds = qty * price * (1 - cfg.slip)
        cash += proceeds
        trade.cash_in += proceeds
        trade.remaining -= qty
        if trade.remaining == 0:
            trade.exit_date, trade.exit_reason = day.date(), reason

    for day in calendar:
        # 1. Entries at today's open from yesterday's signals, in RS-rank order.
        for sig in sorted(pending, key=lambda s: s.rs_rank):
            if any(t.ticker == sig.ticker for t in open_trades):
                skipped["held"] += 1
                continue
            if len(open_trades) >= cfg.max_concurrent:
                skipped["capacity"] += 1
                continue
            frame = frames.get(sig.ticker)
            if frame is None or day not in frame.index:
                skipped["no_bar"] += 1
                continue
            open_px = float(frame.at[day, "Open"])
            if open_px > sig.chase_limit:
                skipped["chase"] += 1
                continue
            if open_px <= sig.stop:
                skipped["invalidated"] += 1
                continue
            fill = open_px * (1 + cfg.slip)
            risk = fill - sig.stop
            shares = position_size(last_equity, params.risk_pct, params.max_position_pct, fill, risk)
            shares = min(shares, int(cash // fill)) if fill > 0 else 0
            if shares <= 0:
                skipped["size"] += 1
                continue
            cash -= shares * fill
            open_trades.append(Trade(
                ticker=sig.ticker, signal_date=sig.signal_date, entry_date=day.date(),
                entry_price=fill, stop=sig.stop, target=fill + params.target_r * risk,
                shares=shares, risk_per_share=risk, remaining=shares, max_close=fill,
            ))
        pending = []

        # 2. Manage open positions on today's bar.
        for trade in open_trades:
            frame = frames[trade.ticker]
            if day not in frame.index:
                continue
            bar = frame.loc[day]
            o, h, low, c = (float(bar[k]) for k in ("Open", "High", "Low", "Close"))
            if trade.exit_next_open:
                sell(trade, trade.remaining, o, day, "trail")
                continue
            if low <= trade.stop:
                sell(trade, trade.remaining, min(o, trade.stop), day, "stop")
                continue
            if not trade.half_taken and h >= trade.target:
                trade.half_taken = trade.trailing = True
                sell(trade, max(1, trade.shares // 2), max(o, trade.target), day, "target")
                if trade.remaining == 0:
                    continue
            trade.days_held += 1
            trade.max_close = max(trade.max_close, c)
            reached_1r = trade.max_close >= trade.entry_price + trade.risk_per_share
            if trade.days_held >= params.max_hold_days and not trade.half_taken:
                if not reached_1r:
                    sell(trade, trade.remaining, c, day, "time")
                    continue
                trade.trailing = True
            if trade.trailing and c < float(ema10[trade.ticker].get(day, np.nan)):
                trade.exit_next_open = True

        still_open = []
        for trade in open_trades:
            (closed if trade.remaining == 0 else still_open).append(trade)
        open_trades = still_open

        # 3. Mark to market.
        mtm = cash
        for trade in open_trades:
            closes = frames[trade.ticker]["Close"]
            px = closes.get(day)
            if px is None or not math.isfinite(float(px)):
                px = closes.loc[:day].iloc[-1]
            mtm += trade.remaining * float(px)
        equity_points[day] = last_equity = mtm
        open_points[day] = len(open_trades)

        # 4. Today's signals become tomorrow's orders.
        pending = by_date.get(day, [])

    last_day = calendar[-1]
    for trade in open_trades:
        px = float(frames[trade.ticker]["Close"].loc[:last_day].iloc[-1])
        sell(trade, trade.remaining, px, last_day, "end_of_data")
        closed.append(trade)

    return SimulationResult(
        trades=sorted(closed, key=lambda t: (t.entry_date, t.ticker)),
        equity=pd.Series(equity_points, dtype=float),
        open_count=pd.Series(open_points, dtype=int),
        skipped=skipped,
    )


# --------------------------------------------------------------------------------------------
# Metrics and baselines
# --------------------------------------------------------------------------------------------


def equity_stats(equity: pd.Series) -> dict:
    """CAGR, max drawdown, Sharpe (rf=0) and the weekly return distribution of a value series."""
    equity = equity.dropna()
    if len(equity) < 2:
        return {}
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    total = equity.iloc[-1] / equity.iloc[0]
    daily = equity.pct_change().dropna()
    weekly = equity.resample("W-FRI").last().pct_change().dropna()
    dd = equity / equity.cummax() - 1
    return {
        "start": str(equity.index[0].date()),
        "end": str(equity.index[-1].date()),
        "total_return_pct": (total - 1) * 100,
        "cagr_pct": (total ** (1 / years) - 1) * 100 if years > 0 else float("nan"),
        "max_drawdown_pct": float(dd.min()) * 100,
        "sharpe": float(daily.mean() / daily.std() * math.sqrt(252)) if daily.std() > 0 else 0.0,
        "median_week_pct": float(weekly.median()) * 100,
        "weeks_ge_2pct": float((weekly >= 0.02).mean()),
        "weeks_le_minus_2pct": float((weekly <= -0.02).mean()),
    }


def trade_stats(trades: list[Trade]) -> dict:
    if not trades:
        return {"trades": 0}
    r = np.array([t.r_multiple for t in trades])
    pnl = np.array([t.pnl for t in trades])
    wins, losses = r[r > 0], r[r <= 0]
    streak = longest = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0
        longest = max(longest, streak)
    gross_loss = -pnl[pnl < 0].sum()
    return {
        "trades": len(trades),
        "win_rate": float((r > 0).mean()),
        "avg_win_r": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_r": float(losses.mean()) if len(losses) else 0.0,
        "expectancy_r": float(r.mean()),
        "expectancy_r_tstat": float(r.mean() / (r.std(ddof=1) / math.sqrt(len(r))))
        if len(r) > 1 and r.std(ddof=1) > 0 else 0.0,
        "profit_factor": float(pnl[pnl > 0].sum() / gross_loss) if gross_loss > 0 else float("inf"),
        "longest_losing_streak": int(longest),
        "avg_days_held": float(np.mean([t.days_held for t in trades])),
        "exit_reasons": pd.Series([t.exit_reason for t in trades]).value_counts().to_dict(),
    }


def summarize(result: SimulationResult) -> dict:
    out = {**trade_stats(result.trades), **equity_stats(result.equity)}
    if len(result.open_count):
        out["time_in_market"] = float((result.open_count > 0).mean())
    out["skipped_entries"] = result.skipped
    return out


def yearly_breakdown(result: SimulationResult) -> pd.DataFrame:
    rows = []
    eq = result.equity
    for year, group in eq.groupby(eq.index.year):
        start = eq[eq.index < group.index[0]]
        base = start.iloc[-1] if len(start) else group.iloc[0]
        ts = [t for t in result.trades if t.entry_date.year == year]
        rows.append({
            "year": int(year),
            "return_pct": (group.iloc[-1] / base - 1) * 100,
            "trades": len(ts),
            "expectancy_r": float(np.mean([t.r_multiple for t in ts])) if ts else float("nan"),
        })
    return pd.DataFrame(rows)


def _close_panel(prices: pd.DataFrame) -> pd.DataFrame:
    panel = prices.assign(Date=pd.to_datetime(prices["Date"])).pivot_table(
        index="Date", columns="ticker", values="Close"
    )
    return panel.sort_index()


def buy_and_hold(prices: pd.DataFrame, ticker: str, start: pd.Timestamp, end: pd.Timestamp,
                 initial: float) -> pd.Series:
    close = _close_panel(prices)[ticker].loc[start:end].dropna()
    return close / close.iloc[0] * initial


def regime_filtered_spy(prices: pd.DataFrame, cfg: BacktestConfig, start: pd.Timestamp,
                        end: pd.Timestamp, initial: float) -> pd.Series:
    """Long SPY only while R1 (SPY > SMA50 and > SMA200) held at the prior close."""
    spy = _close_panel(prices)[BENCHMARK_TICKER].dropna()
    p = cfg.params
    on = (spy > spy.rolling(p.regime_fast_sma).mean()) & (spy > spy.rolling(p.regime_slow_sma).mean())
    held = on.shift(1, fill_value=False)
    ret = spy.pct_change().fillna(0) * held
    switches = held.astype(int).diff().abs().fillna(0)
    ret = ret - switches * cfg.slip
    value = (1 + ret.loc[start:end]).cumprod()
    return value / value.iloc[0] * initial


def top_rs_monthly(prices: pd.DataFrame, universe: list[str], cfg: BacktestConfig,
                   start: pd.Timestamp, end: pd.Timestamp, initial: float) -> pd.Series:
    """Hold the single highest-RS ETF (spec R2 formula), re-chosen at each month-end close."""
    panel = _close_panel(prices)
    spy = panel[BENCHMARK_TICKER]
    tickers = [t for t in universe if t in panel.columns and t != BENCHMARK_TICKER]
    p = cfg.params
    month_ends = panel.loc[start:end].groupby(panel.loc[start:end].index.to_period("M")).tail(1).index
    holding: dict[pd.Timestamp, str] = {}
    for me in month_ends:
        hist = panel.loc[:me]
        s_short = return_over_days(spy.loc[:me].dropna(), p.rs_short_days)
        s_long = return_over_days(spy.loc[:me].dropna(), p.rs_long_days)
        best, best_rs = None, -math.inf
        for t in tickers:
            col = hist[t].dropna()
            r_s, r_l = return_over_days(col, p.rs_short_days), return_over_days(col, p.rs_long_days)
            if None in (r_s, r_l, s_short, s_long):
                continue
            rs = 0.5 * (r_s - s_short) + 0.5 * (r_l - s_long)
            if rs > best_rs:
                best, best_rs = t, rs
        if best:
            holding[me] = best
    daily = panel.pct_change()
    held = pd.Series(holding).reindex(panel.index).ffill().shift(1).loc[start:end]
    rets = []
    prev = None
    for day, ticker in held.items():
        r = 0.0 if not isinstance(ticker, str) else float(daily.at[day, ticker])
        if not math.isfinite(r):
            r = 0.0
        if isinstance(ticker, str) and ticker != prev:
            r -= 2 * cfg.slip if prev else cfg.slip
        rets.append(r)
        prev = ticker if isinstance(ticker, str) else prev
    value = (1 + pd.Series(rets, index=held.index)).cumprod()
    return value / value.iloc[0] * initial
