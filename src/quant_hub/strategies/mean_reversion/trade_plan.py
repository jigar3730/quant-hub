"""Mean reversion trade plan generator."""

from __future__ import annotations

from calendar import month_abbr
from datetime import date, timedelta
from typing import Any

import pandas as pd

from quant_hub.indicators import find_swing_highs, find_swing_lows
from quant_hub.strategies.mean_reversion.constants import (
    BENCHMARK_SYMBOLS,
    DEFENSIVE_SECTORS,
    ENERGY_SECTORS,
    SETUP_LONG,
    SETUP_SHORT,
)
from quant_hub.strategies.mean_reversion.scoring import MeanReversionScoreResult


def _risk_reward(entry: float, stop: float, target: float) -> float | None:
    risk = entry - stop if entry > stop else stop - entry
    if risk <= 0:
        return None
    reward = abs(target - entry)
    return round(reward / risk, 1)


def _format_rr(entry: float, stop: float, target: float) -> str:
    rr = _risk_reward(entry, stop, target)
    if rr is None:
        return "—"
    return f"{rr:.1f} : 1"


def _expiry_range(*, scan_date: date | None = None) -> str:
    scan_date = scan_date or date.today()
    start = scan_date + timedelta(days=45)
    end = scan_date + timedelta(days=90)
    return f"{month_abbr[start.month]}–{month_abbr[end.month]} {end.year}"


def _suggested_delta(ticker: str) -> str:
    if ticker in BENCHMARK_SYMBOLS:
        return "0.65 – 0.80"
    return "0.60 – 0.75"


def _options_type(setup_type: str) -> str:
    if setup_type == SETUP_LONG:
        return "Bull Call Debit Spread"
    return "Bear Put Debit Spread"


def _risk_notes(ticker: str, setup_type: str) -> str:
    if ticker in BENCHMARK_SYMBOLS:
        return "High liquidity benchmark"
    if ticker in DEFENSIVE_SECTORS:
        return "Defensive rotation play"
    if ticker in ENERGY_SECTORS:
        return "Momentum-sensitive sector — confirm hook"
    if setup_type == SETUP_SHORT:
        return "Marginal short — confirm upper BB breach + RSI hook down"
    return "Sector mean reversion setup"


def _stop_loss(
    df: pd.DataFrame,
    *,
    side: str,
    entry: float,
    atr: float,
    lookback: int = 30,
) -> float:
    window = df.tail(lookback)
    if side == "long":
        swings = find_swing_lows(window["Low"], order=2)
        if swings:
            return round(swings[-1][1], 2)
        return round(entry - 1.5 * atr, 2)
    swings = find_swing_highs(window["High"], order=2)
    if swings:
        return round(swings[-1][1], 2)
    return round(entry + 1.5 * atr, 2)


def _entry_trigger(
    *,
    side: str,
    bb_lower: float,
    bb_upper: float,
) -> str:
    if side == "long":
        return f"Close ≤ ~{bb_lower:.0f} + RSI >30"
    return f"Close ≥ ~{bb_upper:.0f} + RSI <70"


def _watchlist_notes(score_result: MeanReversionScoreResult, analysis: Any) -> str:
    if score_result.tier != "WATCHLIST":
        return ""
    side = score_result.scored_side
    rsi = getattr(analysis, "rsi", None)
    if side == "long" and rsi is not None and rsi > 40:
        return "Not extended enough yet"
    if side == "short":
        return "Only if Upper BB breach + RSI hook down"
    if side == "long":
        return "Low Priority — momentum still holding"
    return "Marginal setup — wait for confirmation"


def build_trade_card(
    analysis: Any,
    score_result: MeanReversionScoreResult,
    df: pd.DataFrame,
    *,
    scan_date: date | None = None,
) -> dict:
    """Build trade card dict for HIGH_CONVICTION setups."""
    side = score_result.scored_side
    close = float(analysis.close)
    bb_lower = float(analysis.bb_lower)
    bb_upper = float(analysis.bb_upper)
    bb_mid = float(analysis.bb_mid)
    atr = float(analysis.atr or 0)

    if side == "long":
        entry_est = bb_lower
        target_1 = bb_mid
        target_2 = bb_upper
    else:
        entry_est = bb_upper
        target_1 = bb_mid
        target_2 = bb_lower

    stop = _stop_loss(df, side=side, entry=entry_est, atr=atr)

    return {
        "symbol": analysis.ticker,
        "setup_type": score_result.setup_type,
        "score": score_result.total_score,
        "bias": side,
        "current_price": round(close, 2),
        "entry_trigger": _entry_trigger(side=side, bb_lower=bb_lower, bb_upper=bb_upper),
        "stop_loss": stop,
        "target_1_bb_mean": round(target_1, 2),
        "target_2_opposite_band": round(target_2, 2),
        "options_type": _options_type(score_result.setup_type),
        "expiry_range": _expiry_range(scan_date=scan_date),
        "suggested_delta": _suggested_delta(analysis.ticker),
        "risk_notes": _risk_notes(analysis.ticker, score_result.setup_type),
        "rr_t1": _format_rr(entry_est, stop, target_1),
        "rr_t2": _format_rr(entry_est, stop, target_2),
    }


def build_watchlist_row(
    analysis: Any,
    score_result: MeanReversionScoreResult,
) -> dict:
    return {
        "symbol": analysis.ticker,
        "setup_type": score_result.setup_type,
        "current_price": round(float(analysis.close), 2),
        "score": score_result.total_score,
        "status": "Watch" if score_result.scored_side == "long" else "Marginal Short",
        "notes": _watchlist_notes(score_result, analysis),
    }
