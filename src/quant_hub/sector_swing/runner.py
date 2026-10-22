"""Sector-ETF swing scan orchestration.

``scan_prices`` is pure (a price frame in, outcomes out) so it can be replayed point-in-time
(``as_of``) and unit-tested without network. ``SectorSwingRunner`` wraps it with price loading,
the data-freshness gate and report assembly.

Failures are isolated per ticker (``compute_error``); a missing benchmark or stale data aborts
the whole run.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from quant_hub.config import BENCHMARK_TICKER
from quant_hub.data.quality import max_bar_date, validate_ohlcv
from quant_hub.engine.context import synthetic_prices, ticker_df
from quant_hub.indicators import return_over_days, sma
from quant_hub.infrastructure.market.yfinance_provider import download_prices
from quant_hub.ml.backfill_dates import truncate_daily_to_date
from quant_hub.regime.market import regime_detail
from quant_hub.sector_swing import config as C
from quant_hub.sector_swing import rules
from quant_hub.sector_swing.calendar import expected_last_session
from quant_hub.sector_swing.config import SwingParams
from quant_hub.sector_swing.indicators import compute_indicators
from quant_hub.sector_swing.models import RuleResult, TickerOutcome
from quant_hub.sector_swing.positions import (
    PortfolioState,
    Position,
    PositionStatus,
    evaluate_position,
    week_start,
)
from quant_hub.sector_swing.report import build_report, outcomes_to_dataframe
from quant_hub.sector_swing.sizing import build_trade_plan

logger = logging.getLogger(__name__)

PriceLoader = Callable[..., pd.DataFrame]


class SectorSwingError(RuntimeError):
    """Run-level failure: nothing should be persisted."""


class MissingBenchmarkError(SectorSwingError):
    pass


class StaleDataError(SectorSwingError):
    pass


@dataclass
class ScanResult:
    outcomes: list[TickerOutcome]
    regime: dict
    regime_check: RuleResult
    spy_as_of: date
    portfolio: PortfolioState | None = None

    @property
    def regime_gate_passed(self) -> bool:
        return self.regime_check.passed


def _frame(prices: pd.DataFrame, ticker: str, as_of: date | None) -> pd.DataFrame | None:
    df = ticker_df(prices, ticker)
    if df is None:
        return None
    if as_of is not None:
        df = truncate_daily_to_date(df, as_of)
        if df is None or df.empty:
            return None
    return df


def _returns(df: pd.DataFrame, window: int) -> pd.Series:
    close = df.set_index(pd.to_datetime(df["Date"]))["Close"].astype(float)
    return close.pct_change().dropna().tail(window)


def _hygiene_reason(df: pd.DataFrame | None, params: SwingParams) -> str | None:
    """Rule H. Returns a filter reason, or None when the ticker is usable."""
    if df is None:
        return C.REASON_NO_PRICE_DATA
    if len(df) < params.min_bars:
        return C.REASON_INSUFFICIENT_HISTORY
    recent = df.tail(params.min_bars)
    cols = [c for c in ("High", "Low", "Close", "Volume") if c in recent.columns]
    if len(cols) < 4 or recent[cols].isna().any().any():
        return C.REASON_DATA_QUALITY
    if not validate_ohlcv(df, min_rows=params.min_bars).ok:
        return C.REASON_DATA_QUALITY
    dollar_volume = (
        (recent["Close"].astype(float) * recent["Volume"].astype(float))
        .tail(params.liquidity_window)
        .mean()
    )
    if dollar_volume < params.min_avg_dollar_volume or float(df["Close"].iloc[-1]) < params.min_price:
        return C.REASON_ILLIQUID
    return None


def _evaluate_setup(
    outcome: TickerOutcome,
    params: SwingParams,
    *,
    regime_check: RuleResult,
    equity: float,
    risk_pct: float,
) -> bool:
    """Walk R2-R7 for one ticker. Returns True when it is a Tier 1 candidate (pre portfolio gates).

    Sets ``outcome.tier`` / ``reason`` / ``plan`` for every other terminal state.
    """
    ind = outcome.indicators
    assert ind is not None

    leader = rules.check_leader(outcome.rs_rank, outcome.rs_score_pct, params)
    outcome.checks.append(leader)
    if not leader.passed:
        outcome.tier, outcome.reason = C.TIER_FILTERED, C.REASON_NOT_LEADER
        return False

    trend = rules.check_trend(ind, params)
    outcome.checks.append(trend)
    if not trend.passed:
        outcome.tier, outcome.reason = C.TIER_FILTERED, C.REASON_TREND_FAIL
        return False

    pullback = rules.check_pullback(ind, params)
    outcome.checks.append(pullback)
    if not pullback.passed:
        outcome.tier = C.TIER_EXTENDED
        return False

    trigger = rules.check_trigger(ind, params)
    outcome.checks.append(trigger)
    if not trigger.passed:
        outcome.tier = C.TIER_WATCH
        return False

    stop_check, stop, risk = rules.check_stop(ind, params)
    outcome.checks.append(stop_check)
    if not stop_check.passed:
        outcome.tier, outcome.reason = C.TIER_FILTERED, C.REASON_STOP_TOO_WIDE
        return False

    plan = build_trade_plan(
        ind,
        params,
        stop=stop,
        risk_per_share=risk,
        equity=equity,
        risk_pct=risk_pct,
        regime_blocked=not regime_check.passed,
    )
    size_ok = plan.shares > 0
    outcome.checks.append(
        RuleResult(
            rule="R7_sizing",
            passed=size_ok,
            value=float(plan.shares),
            threshold=f"shares >= 1 at {risk_pct:.2%} risk, {params.max_position_pct:.0%} max position",
        )
    )
    if not size_ok:
        outcome.tier, outcome.reason = C.TIER_FILTERED, C.REASON_SIZE_ZERO
        return False

    outcome.plan = plan
    if not regime_check.passed:
        # Would qualify but the market gate is off: informational levels only.
        outcome.tier = C.TIER_WATCH
        outcome.regime_blocked = True
        return False
    return True


def _apply_portfolio_gates(
    candidates: list[TickerOutcome],
    frames: dict[str, pd.DataFrame],
    params: SwingParams,
    held: dict[str, pd.DataFrame | None] | None = None,
) -> None:
    """Walk candidates in RS-rank order: skip ETFs already held, cap new signals (per scan and
    against open positions), skip near-duplicates of a selected plan or an open position.

    ``held`` maps each open-position ticker to its price frame (None when unavailable).
    """
    held = held or {}
    selected: list[TickerOutcome] = []
    returns: dict[str, pd.Series] = {}
    slots = max(0, params.max_open_positions - len(held))
    cap = min(params.max_new_signals, slots)

    def series(ticker: str) -> pd.Series:
        if ticker not in returns:
            frame = frames.get(ticker)
            if frame is None:
                frame = held[ticker]
            returns[ticker] = _returns(frame, params.corr_window)
        return returns[ticker]

    def demote(cand: TickerOutcome, reason: str) -> None:
        cand.tier, cand.reason, cand.plan = C.TIER_FILTERED, reason, None

    for cand in sorted(candidates, key=lambda o: o.rs_rank or 10**6):
        if cand.ticker in held:
            cand.checks.append(
                RuleResult("P_already_open", False, None, "no open position in this ETF")
            )
            demote(cand, C.REASON_ALREADY_OPEN)
            continue

        if len(selected) >= cap:
            if len(held) + len(selected) >= params.max_open_positions:
                cand.checks.append(
                    RuleResult("P_position_limit", False, float(len(held) + len(selected)),
                               f"at most {params.max_open_positions} open positions "
                               f"({len(held)} open)")
                )
                demote(cand, C.REASON_POSITION_LIMIT)
            else:
                cand.checks.append(
                    RuleResult("P_signal_cap", False, float(len(selected)),
                               f"at most {params.max_new_signals} new signals per scan")
                )
                demote(cand, C.REASON_SIGNAL_CAP)
            continue

        others = [t for t, f in held.items() if f is not None] + [o.ticker for o in selected]
        blocker: tuple[str, float] | None = None
        worst: tuple[str, float] | None = None
        for other in others:
            label = f"{other} (open)" if other in held else other
            pair = pd.concat(
                [series(cand.ticker), series(other)], axis=1, join="inner"
            ).dropna()
            if len(pair) < params.corr_min_overlap:
                logger.warning(
                    "Correlation gate skipped for %s vs %s: only %d overlapping returns",
                    cand.ticker, label, len(pair),
                )
                continue
            corr = (
                float(pair.iloc[:, 0].corr(pair.iloc[:, 1]))
                if (pair.std() > 0).all()
                else float("nan")
            )
            if not math.isfinite(corr):  # zero-variance series (e.g. frozen price)
                logger.warning(
                    "Correlation gate skipped for %s vs %s: correlation undefined",
                    cand.ticker, label,
                )
                continue
            if worst is None or corr > worst[1]:
                worst = (label, corr)
            if corr > params.corr_max:
                blocker = (label, corr)
                break

        if blocker is not None:
            cand.checks.append(
                RuleResult("P_correlation", False, blocker[1],
                           f"{params.corr_window}d return corr <= {params.corr_max:g} vs "
                           f"{blocker[0]}")
            )
            demote(cand, C.REASON_CORRELATED)
            continue

        if worst is not None:
            cand.checks.append(
                RuleResult("P_correlation", True, worst[1],
                           f"{params.corr_window}d return corr <= {params.corr_max:g} vs "
                           f"{worst[0]}")
            )
        cand.tier = C.TIER_TRIGGER
        selected.append(cand)


def scan_prices(
    prices: pd.DataFrame,
    universe: list[str],
    *,
    params: SwingParams = C.DEFAULT_PARAMS,
    equity: float,
    risk_pct: float,
    as_of: date | None = None,
    portfolio: PortfolioState | None = None,
) -> ScanResult:
    """Pure scan over an already-loaded long price frame (benchmark included).

    ``as_of`` truncates every series to bars on or before that date (point-in-time replay).
    ``portfolio`` adds the Phase 2 open-position gates; its tickers' prices should be in
    ``prices`` (needed for the correlation gate) even when they are outside ``universe``.
    """
    spy_df = _frame(prices, BENCHMARK_TICKER, as_of)
    if spy_df is None or spy_df.empty:
        raise MissingBenchmarkError(f"Missing benchmark data for {BENCHMARK_TICKER}")
    try:
        regime = regime_detail(spy_df)
    except RuntimeError as exc:
        raise MissingBenchmarkError(str(exc)) from exc

    spy_close = spy_df["Close"].astype(float)
    regime_check = rules.check_regime(
        float(spy_close.iloc[-1]),
        float(sma(spy_close, params.regime_fast_sma).iloc[-1]),
        float(sma(spy_close, params.regime_slow_sma).iloc[-1]),
    )
    spy_short = return_over_days(spy_close, params.rs_short_days)
    spy_long = return_over_days(spy_close, params.rs_long_days)
    if spy_short is None or spy_long is None:
        raise MissingBenchmarkError("Insufficient SPY history for relative-strength windows")

    outcomes: dict[str, TickerOutcome] = {}
    frames: dict[str, pd.DataFrame] = {}
    tickers = [t for t in dict.fromkeys(universe) if t != BENCHMARK_TICKER]

    # Phase A: hygiene + indicators, isolated per ticker.
    for ticker in tickers:
        try:
            df = _frame(prices, ticker, as_of)
            reason = _hygiene_reason(df, params)
            if reason:
                outcomes[ticker] = TickerOutcome(ticker, C.TIER_FILTERED, reason)
                continue
            assert df is not None
            ind = compute_indicators(df, params)
            outcome = TickerOutcome(
                ticker,
                C.TIER_FILTERED,
                indicators=ind,
                rs_score_pct=rules.relative_strength_pct(ind, spy_short, spy_long),
            )
            outcome.checks.append(regime_check)
            if outcome.rs_score_pct is None:
                outcome.reason = C.REASON_INSUFFICIENT_HISTORY
            outcomes[ticker] = outcome
            frames[ticker] = df
        except Exception as exc:  # noqa: BLE001 — one bad ticker must not abort the scan
            logger.exception("Sector swing compute failed for %s", ticker)
            outcomes[ticker] = TickerOutcome(
                ticker, C.TIER_FILTERED, C.REASON_COMPUTE_ERROR, error=f"{type(exc).__name__}: {exc}"
            )
            frames.pop(ticker, None)

    # Phase B: relative-strength rank among tickers that passed hygiene.
    ranked = sorted(
        (o for o in outcomes.values() if o.indicators is not None and o.rs_score_pct is not None),
        key=lambda o: (-o.rs_score_pct, o.ticker),
    )
    for rank, outcome in enumerate(ranked, start=1):
        outcome.rs_rank = rank

    # Phase C: rules R2-R7 per ticker, isolated.
    candidates: list[TickerOutcome] = []
    for outcome in ranked:
        try:
            if _evaluate_setup(outcome, params, regime_check=regime_check,
                               equity=equity, risk_pct=risk_pct):
                candidates.append(outcome)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Sector swing rule evaluation failed for %s", outcome.ticker)
            outcome.tier, outcome.reason, outcome.plan = C.TIER_FILTERED, C.REASON_COMPUTE_ERROR, None
            outcome.error = f"{type(exc).__name__}: {exc}"

    # Phase D: portfolio-level gates.
    held: dict[str, pd.DataFrame | None] = {}
    for ticker in portfolio.open_tickers if portfolio else ():
        held[ticker] = frames.get(ticker)
        if held[ticker] is None:
            held[ticker] = _frame(prices, ticker, as_of)
        if held[ticker] is None:
            logger.warning("No prices for open position %s; correlation vs it is skipped", ticker)
    try:
        _apply_portfolio_gates(candidates, frames, params, held)
    except Exception as exc:  # noqa: BLE001
        # Fail safe: never issue an un-gated plan.
        logger.exception("Portfolio gates failed; demoting %d candidates", len(candidates))
        for cand in candidates:
            cand.tier, cand.reason, cand.plan = C.TIER_FILTERED, C.REASON_COMPUTE_ERROR, None
            cand.error = f"portfolio gate: {type(exc).__name__}: {exc}"

    spy_as_of = max_bar_date(spy_df)
    assert spy_as_of is not None
    return ScanResult(
        outcomes=[outcomes[t] for t in tickers],
        regime=regime,
        regime_check=regime_check,
        spy_as_of=spy_as_of,
        portfolio=portfolio,
    )


def _clip_to_session(prices: pd.DataFrame, session: date) -> pd.DataFrame:
    """Drop bars dated after the last completed session (a partial 'today' bar)."""
    if prices.empty:
        return prices
    return prices[pd.to_datetime(prices["Date"]).dt.date <= session].copy()


class SectorSwingRunner:
    def __init__(
        self,
        *,
        universe: list[str],
        universe_id: str = C.UNIVERSE_ID,
        params: SwingParams = C.DEFAULT_PARAMS,
        equity: float | None = None,
        risk_pct: float | None = None,
        use_cache: bool = True,
        dry_run: bool = False,
        allow_stale: bool = False,
        now: datetime | None = None,
        price_loader: PriceLoader | None = None,
        scan_date: date | None = None,
        positions: list[Position] | None = None,
        week_realized_pnl: float = 0.0,
    ) -> None:
        self.universe = [t for t in dict.fromkeys(universe) if t != BENCHMARK_TICKER]
        self.universe_id = universe_id
        self.params = params
        self.equity = C.resolve_equity(equity)
        self.risk_pct = params.risk_pct if risk_pct is None else float(risk_pct)
        self.use_cache = use_cache
        self.dry_run = dry_run
        self.allow_stale = allow_stale
        self.now = now
        self.price_loader = price_loader or download_prices
        self.scan_date = scan_date or date.today()
        self.positions = list(positions or [])
        self.week_realized_pnl = float(week_realized_pnl)
        # Filled by run(): each open position's refreshed status (None when it failed).
        self.position_updates: list[tuple[Position, PositionStatus | None]] = []

    def _load_prices(self) -> tuple[pd.DataFrame, str, date | None]:
        """Returns (prices, data_freshness, expected_session). Aborts on stale/missing data."""
        tickers = sorted({*self.universe, *(p.ticker for p in self.positions), BENCHMARK_TICKER})
        if self.dry_run:
            return synthetic_prices(tickers), C.FRESHNESS_SYNTHETIC, None

        expected = expected_last_session(self.now)
        prices = _clip_to_session(self.price_loader(tickers, use_cache=self.use_cache), expected)
        freshness = C.FRESHNESS_FRESH
        spy_last = max_bar_date(ticker_df(prices, BENCHMARK_TICKER))

        if (spy_last is None or spy_last < expected) and self.use_cache:
            logger.warning(
                "SPY last bar %s is older than expected session %s; refetching bypassing cache",
                spy_last, expected,
            )
            prices = _clip_to_session(self.price_loader(tickers, use_cache=False), expected)
            freshness = C.FRESHNESS_REFRESHED
            spy_last = max_bar_date(ticker_df(prices, BENCHMARK_TICKER))

        if spy_last is None:
            raise MissingBenchmarkError(f"No {BENCHMARK_TICKER} price data available")
        if spy_last < expected:
            if not self.allow_stale:
                raise StaleDataError(
                    f"Stale price data: {BENCHMARK_TICKER} last bar {spy_last}, expected "
                    f"{expected}. Aborting (use --allow-stale to override)."
                )
            logger.warning("Proceeding on stale data (%s < %s): --allow-stale", spy_last, expected)
            freshness = C.FRESHNESS_STALE_ALLOWED
        return prices, freshness, expected

    def _refresh_positions(self, prices: pd.DataFrame) -> None:
        """Re-evaluate every open position on the scan's prices, isolated per position."""
        self.position_updates = []
        for pos in self.positions:
            try:
                df = ticker_df(prices, pos.ticker)
                if df is None or df.empty:
                    raise ValueError("no price data")
                self.position_updates.append((pos, evaluate_position(pos, df, self.params)))
            except Exception:  # noqa: BLE001 — one bad position must not abort the scan
                logger.exception("Position refresh failed for %s (id %s)", pos.ticker, pos.id)
                self.position_updates.append((pos, None))

    def run(self) -> tuple[pd.DataFrame, dict]:
        prices, freshness, expected = self._load_prices()
        portfolio = PortfolioState(
            open_tickers=tuple(sorted({p.ticker for p in self.positions})),
            week_start=week_start(self.scan_date),
            week_realized_pnl=self.week_realized_pnl,
        )
        result = scan_prices(
            prices,
            self.universe,
            params=self.params,
            equity=self.equity,
            risk_pct=self.risk_pct,
            portfolio=portfolio,
        )
        if not self.dry_run:
            self._refresh_positions(prices)
        report = build_report(
            result,
            universe=self.universe,
            universe_id=self.universe_id,
            params=self.params,
            equity=self.equity,
            risk_pct=self.risk_pct,
            data_freshness=freshness,
            expected_session=expected,
            scan_date=self.scan_date,
            price_cache="live" if (not self.use_cache or self.dry_run) else "parquet",
            dry_run=self.dry_run,
        )
        summary = report["scan_summary"]
        logger.info(
            "Sector swing scan complete: %d Tier 1 / %d Tier 2 / %d Tier 3 / %d filtered "
            "(regime gate %s, as of %s, freshness=%s)",
            summary["tier_counts"][C.TIER_TRIGGER],
            summary["tier_counts"][C.TIER_WATCH],
            summary["tier_counts"][C.TIER_EXTENDED],
            summary["tier_counts"][C.TIER_FILTERED],
            "PASS" if result.regime_gate_passed else "FAIL",
            result.spy_as_of,
            freshness,
        )
        return outcomes_to_dataframe(result.outcomes), report
