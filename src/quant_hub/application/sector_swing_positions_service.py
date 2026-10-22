"""Sector-ETF swing paper positions (Phase 2): log fills by hand, refresh exit signals.

Research tool only: nothing here talks to a broker. Opening a position defaults its stop to the
latest scan's trade plan for that ETF; R and the 2R target are re-based on the actual fill.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from quant_hub.config import BENCHMARK_TICKER
from quant_hub.data.quality import max_bar_date
from quant_hub.engine.context import ticker_df
from quant_hub.infrastructure.market.yfinance_provider import download_prices
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository
from quant_hub.infrastructure.postgres.sector_swing_positions_repository import (
    PositionError,
    SectorSwingPositionsRepository,
)
from quant_hub.sector_swing import config as C
from quant_hub.sector_swing.calendar import expected_last_session
from quant_hub.sector_swing.config import SwingParams
from quant_hub.sector_swing.positions import (
    SIGNAL_ACTION,
    Position,
    PositionStatus,
    evaluate_position,
    target_price,
)

logger = logging.getLogger(__name__)


@dataclass
class OpenResult:
    position: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


@dataclass
class RefreshResult:
    as_of: date | None
    expected_session: date
    updated: list[tuple[dict[str, Any], PositionStatus]] = field(default_factory=list)
    failed: list[tuple[dict[str, Any], str]] = field(default_factory=list)

    @property
    def stale(self) -> bool:
        return self.as_of is None or self.as_of < self.expected_session


def realized_r(position: dict[str, Any]) -> float | None:
    """Realized P&L in R (initial risk x initial shares)."""
    risk = (position["entry_price"] - position["initial_stop"]) * position["initial_shares"]
    return position["realized_pnl"] / risk if risk > 0 else None


def suggested_action(position: dict[str, Any]) -> str | None:
    signal = position.get("exit_signal")
    return SIGNAL_ACTION.get(signal) if signal else None


class SectorSwingPositionsService:
    def __init__(
        self,
        *,
        repo: SectorSwingPositionsRepository | None = None,
        scan_repo: ScanRepository | None = None,
        job_repo: JobRunRepository | None = None,
        params: SwingParams = C.DEFAULT_PARAMS,
        price_loader: Callable[..., pd.DataFrame] = download_prices,
    ) -> None:
        self.repo = repo or SectorSwingPositionsRepository()
        self.scan_repo = scan_repo or ScanRepository()
        self.job_repo = job_repo or JobRunRepository()
        self.params = params
        self.price_loader = price_loader

    def latest_plan(self, ticker: str) -> tuple[int | None, dict[str, Any] | None, str | None]:
        """(run_id, trade_plan, tier) for ``ticker`` from the latest persisted sector-swing scan."""
        run = self.scan_repo.get_latest_run(strategy_id=C.STRATEGY_ID, universe_id=C.UNIVERSE_ID)
        if not run:
            return None, None, None
        for detail in self.scan_repo.list_ticker_details_for_run(run["id"]):
            if detail.get("ticker") == ticker:
                return run["id"], detail.get("trade_plan"), detail.get("tier")
        return run["id"], None, None

    def open_position(
        self,
        ticker: str,
        *,
        price: float,
        shares: int,
        entry_date: date | None = None,
        stop: float | None = None,
        trail_mode: str | None = None,
        notes: str | None = None,
    ) -> OpenResult:
        ticker = ticker.strip().upper()
        if price <= 0 or shares <= 0:
            raise PositionError("Entry price and shares must be positive")
        entry_date = entry_date or date.today()
        warnings: list[str] = []

        run_id, plan, tier = self.latest_plan(ticker)
        if plan is None:
            warnings.append(f"No trade plan for {ticker} in the latest scan")
        else:
            if tier != C.TIER_TRIGGER:
                warnings.append(
                    f"{ticker} is {tier} in the latest scan (not a Tier 1 trigger)"
                    + ("; its plan is regime-blocked" if plan.get("regime_blocked") else "")
                )
            chase = plan.get("chase_limit")
            if chase is not None and price > chase:
                warnings.append(
                    f"Fill {price:.2f} is above the plan's chase limit {chase:.2f} "
                    "(the plan says skip)"
                )
        if stop is None:
            if plan is None:
                raise PositionError(f"No scan plan for {ticker}; pass --stop explicitly")
            stop = float(plan["stop"])
        if price <= stop:
            raise PositionError(f"Entry {price:.2f} must be above the stop {stop:.2f}")

        open_count = len(self.repo.list_positions(status="open"))
        if open_count >= self.params.max_open_positions:
            warnings.append(
                f"{open_count} positions already open (limit {self.params.max_open_positions})"
            )

        mode = trail_mode or self.params.trail_mode
        position_id = self.repo.insert_position(
            ticker=ticker,
            entry_date=entry_date,
            entry_price=price,
            shares=shares,
            initial_stop=stop,
            target_price=target_price(price, stop, self.params),
            trail_mode=mode,
            max_hold_days=self.params.max_hold_days,
            source_run_id=run_id if plan is not None else None,
            notes=notes,
        )
        position = self.repo.get_position(position_id)
        assert position is not None
        return OpenResult(position=position, warnings=warnings)

    def resolve(self, ref: str) -> dict[str, Any]:
        """A position by numeric id, or the open position for a ticker."""
        position = (
            self.repo.get_position(int(ref)) if ref.isdigit()
            else self.repo.get_open_by_ticker(ref.strip().upper())
        )
        if position is None:
            raise PositionError(f"No position matching {ref!r}")
        return position

    def sell(
        self,
        ref: str,
        *,
        price: float,
        shares: int | None = None,
        fill_date: date | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Record a sell; ``shares=None`` sells everything still open."""
        position = self.resolve(ref)
        qty = position["open_shares"] if shares is None else shares
        return self.repo.record_sell(
            position["id"],
            fill_date=fill_date or date.today(),
            price=price,
            shares=qty,
            reason=reason or position.get("exit_signal") or "manual",
        )

    def _load(self, tickers: list[str], use_cache: bool, session: date) -> pd.DataFrame:
        prices = self.price_loader(tickers, use_cache=use_cache)
        if prices.empty:
            return prices
        # Drop a partial 'today' bar, as the scanner does.
        return prices[pd.to_datetime(prices["Date"]).dt.date <= session]

    def refresh(self, *, use_cache: bool = True, now: datetime | None = None) -> RefreshResult:
        """Recompute every open position's stop / exit signal on fresh prices."""
        expected = expected_last_session(now)
        rows = self.repo.list_positions(status="open")
        if not rows:
            return RefreshResult(as_of=None, expected_session=expected)

        job_id = self.job_repo.start_job(C.POSITIONS_JOB_NAME, tickers_requested=len(rows))
        try:
            tickers = sorted({row["ticker"] for row in rows} | {BENCHMARK_TICKER})
            prices = self._load(tickers, use_cache, expected)
            as_of = max_bar_date(ticker_df(prices, BENCHMARK_TICKER))
            if use_cache and (as_of is None or as_of < expected):
                # Same rule as the scanner: a stale cache gets one cache-bypassing refetch.
                logger.warning("Cached prices end %s (< %s); refetching", as_of, expected)
                prices = self._load(tickers, False, expected)
                as_of = max_bar_date(ticker_df(prices, BENCHMARK_TICKER))
            result = RefreshResult(as_of=as_of, expected_session=expected)
            for row in rows:
                try:
                    df = ticker_df(prices, row["ticker"])
                    if df is None or df.empty:
                        raise ValueError("no price data")
                    status = evaluate_position(Position.from_row(row), df, self.params)
                    self.repo.update_tracking(row["id"], status.to_row())
                    result.updated.append((row, status))
                except Exception as exc:  # noqa: BLE001 — isolate per position
                    logger.exception("Position refresh failed for %s", row["ticker"])
                    result.failed.append((row, f"{type(exc).__name__}: {exc}"))
            self.job_repo.finish_job(
                job_id,
                status="success" if result.updated or not result.failed else "failed",
                tickers_fetched=len(result.updated),
                tickers_failed=len(result.failed),
            )
            return result
        except Exception as exc:
            self.job_repo.finish_job(job_id, status="failed", error_message=str(exc))
            raise
