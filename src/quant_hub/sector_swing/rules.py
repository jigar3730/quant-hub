"""Pure rule functions R1-R6. Thresholds come from ``SwingParams``; no I/O, no globals."""

from __future__ import annotations

from quant_hub.sector_swing.config import SwingParams
from quant_hub.sector_swing.models import RuleResult, SwingIndicators

_EPS = 1e-9


def check_regime(spy_close: float, sma50: float, sma200: float) -> RuleResult:
    """R1: SPY above both its 50- and 200-day SMA (unrounded inputs)."""
    passed = spy_close > sma50 and spy_close > sma200
    return RuleResult(
        rule="R1_regime",
        passed=passed,
        value=spy_close,
        threshold=f"SPY > SMA50 ({sma50:.2f}) and > SMA200 ({sma200:.2f})",
    )


def relative_strength_pct(
    ind: SwingIndicators, spy_short: float | None, spy_long: float | None
) -> float | None:
    """R2 score in percentage points: mean of the 63d and 126d excess return over SPY."""
    if None in (ind.ret_short, ind.ret_long, spy_short, spy_long):
        return None
    excess = 0.5 * (ind.ret_short - spy_short) + 0.5 * (ind.ret_long - spy_long)
    return float(excess) * 100.0


def check_leader(rank: int | None, rs_pct: float | None, params: SwingParams) -> RuleResult:
    """R2: top-N by RS and (optionally) RS strictly positive."""
    passed = bool(
        rank is not None
        and rs_pct is not None
        and rank <= params.top_n_leaders
        and (rs_pct > 0 or not params.require_positive_rs)
    )
    positive = " and RS > 0" if params.require_positive_rs else ""
    return RuleResult(
        rule="R2_leadership",
        passed=passed,
        value=rs_pct,
        threshold=f"RS rank <= {params.top_n_leaders}{positive}",
    )


def check_trend(ind: SwingIndicators, params: SwingParams) -> RuleResult:
    """R3: Close > SMA50, EMA20 > SMA50, ADX >= minimum. ``value`` is the ADX."""
    passed = (
        ind.close > ind.sma50 and ind.ema20 > ind.sma50 and ind.adx14 >= params.adx_min
    )
    return RuleResult(
        rule="R3_trend",
        passed=passed,
        value=ind.adx14,
        threshold=(
            f"Close > SMA{params.sma_trend}, EMA{params.ema_mid} > SMA{params.sma_trend}, "
            f"ADX{params.adx_window} >= {params.adx_min:g}"
        ),
    )


def check_pullback(ind: SwingIndicators, params: SwingParams) -> RuleResult:
    """R4: within the last N bars a Low touched EMA20 x tolerance. ``value`` = tightest Low/EMA."""
    ratios = [low / e for low, e in zip(ind.lows_recent, ind.ema20_recent, strict=True)]
    tightest = min(ratios)
    return RuleResult(
        rule="R4_pullback",
        passed=tightest <= params.pullback_tolerance + _EPS,
        value=tightest,
        threshold=(
            f"min Low/EMA{params.ema_mid} <= {params.pullback_tolerance:g} "
            f"within last {params.pullback_lookback} bars"
        ),
    )


def check_trigger(ind: SwingIndicators, params: SwingParams) -> RuleResult:
    """R5: signal-bar Close > prior High and Close > EMA10."""
    passed = ind.close > ind.prev_high and ind.close > ind.ema10
    return RuleResult(
        rule="R5_trigger",
        passed=passed,
        value=ind.close,
        threshold=(
            f"Close > prior High ({ind.prev_high:.2f}) and > EMA{params.ema_fast} "
            f"({ind.ema10:.2f})"
        ),
    )


def compute_stop(ind: SwingIndicators, params: SwingParams) -> tuple[float, float, float]:
    """R6 levels: (stop, risk_per_share, risk in ATR multiples)."""
    stop = ind.pullback_low - params.stop_atr_buffer * ind.atr14
    risk = ind.close - stop
    multiple = risk / ind.atr14 if ind.atr14 > 0 else float("inf")
    return stop, risk, multiple


def check_stop(ind: SwingIndicators, params: SwingParams) -> tuple[RuleResult, float, float]:
    """R6: reject when risk <= 0 or wider than MAX_STOP_ATR x ATR. Returns (result, stop, risk)."""
    stop, risk, multiple = compute_stop(ind, params)
    passed = risk > 0 and ind.atr14 > 0 and risk <= params.max_stop_atr * ind.atr14 + _EPS
    result = RuleResult(
        rule="R6_stop",
        passed=passed,
        value=multiple,
        threshold=f"0 < entry - stop <= {params.max_stop_atr:g} x ATR{params.atr_window}",
    )
    return result, stop, risk
