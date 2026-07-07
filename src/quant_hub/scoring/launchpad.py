"""Launchpad Reversal scoring and eligibility helpers."""

from __future__ import annotations

import pandas as pd

from quant_hub.config import (
    LAUNCHPAD_ATR_LONG_WINDOW,
    LAUNCHPAD_ATR_RATIO_OK,
    LAUNCHPAD_ATR_RATIO_STRONG,
    LAUNCHPAD_ATR_SHORT_WINDOW,
    LAUNCHPAD_MACD_ZERO_CROSS_LOOKBACK,
    LAUNCHPAD_MIN_AVG_VOLUME,
    LAUNCHPAD_MIN_HISTORY_DAYS,
    LAUNCHPAD_SWING_DEDUPE_MIN_GAP,
    LAUNCHPAD_SWING_HISTORY_DAYS,
    LAUNCHPAD_VCP_RATIO_OK,
    LAUNCHPAD_VCP_RATIO_STRONG,
    LAUNCHPAD_VOLUME_DRYUP_LONG_WINDOW,
    LAUNCHPAD_VOLUME_DRYUP_OK,
    LAUNCHPAD_VOLUME_DRYUP_SHORT_WINDOW,
    LAUNCHPAD_VOLUME_DRYUP_STRONG,
)
from quant_hub.indicators import (
    atr,
    find_swing_highs,
    find_swing_lows,
    macd_line,
    macd_signal,
    sma,
)

FILTER_LABELS = {
    "insufficient_history": f"Fewer than {LAUNCHPAD_MIN_HISTORY_DAYS} trading days of history",
    "no_price_data": "No price data available",
    "base_not_cleared": "Price not above both SMA50 and SMA200",
    "trend_not_fresh": "SMA50 is not rising vs 10 trading days ago",
    "too_extended": "Price more than 8% above 20-day median close",
    "low_liquidity": f"20-day average volume below {LAUNCHPAD_MIN_AVG_VOLUME:,} shares",
    "eligible": "Passed all eligibility filters",
}


def launchpad_eligibility_detail(df: pd.DataFrame) -> dict:
    """Return structured eligibility checks for Launchpad Reversal."""
    checks: list[dict] = []

    if df is None or df.empty:
        return _fail(checks, "no_price_data")

    history_len = len(df)
    checks.append(
        {
            "rule": "trading_history",
            "passed": history_len >= LAUNCHPAD_MIN_HISTORY_DAYS,
            "value": history_len,
            "threshold": f">= {LAUNCHPAD_MIN_HISTORY_DAYS} days",
        }
    )
    if history_len < LAUNCHPAD_MIN_HISTORY_DAYS:
        return _fail(checks, "insufficient_history")

    close = df["Close"]
    price = float(close.iloc[-1])
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    s50 = float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else None
    s200 = float(sma200.iloc[-1]) if not pd.isna(sma200.iloc[-1]) else None

    if s50 is None or s200 is None:
        checks.append(
            {
                "rule": "moving_averages",
                "passed": False,
                "value": None,
                "threshold": "SMA50/200 computable",
            }
        )
        return _fail(checks, "insufficient_history")

    base_ok = price > s50 and price > s200
    checks.append(
        {
            "rule": "base_clearance",
            "passed": base_ok,
            "value": {"price": round(price, 2), "sma50": round(s50, 2), "sma200": round(s200, 2)},
            "threshold": "price > SMA50 AND price > SMA200",
        }
    )
    if not base_ok:
        return _fail(checks, "base_not_cleared")

    sma50_10d = float(sma50.iloc[-11]) if len(sma50) >= 11 and not pd.isna(sma50.iloc[-11]) else None
    trend_fresh = sma50_10d is not None and s50 > sma50_10d
    checks.append(
        {
            "rule": "fresh_trend",
            "passed": trend_fresh,
            "value": {
                "sma50_today": round(s50, 2),
                "sma50_10d_ago": round(sma50_10d, 2) if sma50_10d is not None else None,
            },
            "threshold": "SMA50 today > SMA50 10 trading days ago",
        }
    )
    if not trend_fresh:
        return _fail(checks, "trend_not_fresh")

    median20 = float(close.tail(20).median())
    extension = (price - median20) / median20 if median20 else None
    not_extended = extension is not None and extension <= 0.08
    checks.append(
        {
            "rule": "not_extended",
            "passed": not_extended,
            "value": {
                "price": round(price, 2),
                "median20": round(median20, 2),
                "pct_above_median": round(extension * 100, 2) if extension is not None else None,
            },
            "threshold": "price <= 8% above 20-day median close",
        }
    )
    if not not_extended:
        return _fail(checks, "too_extended")

    avg_vol = float(df["Volume"].tail(20).mean())
    liquidity_ok = avg_vol >= LAUNCHPAD_MIN_AVG_VOLUME
    checks.append(
        {
            "rule": "liquidity",
            "passed": liquidity_ok,
            "value": int(avg_vol),
            "threshold": f">= {LAUNCHPAD_MIN_AVG_VOLUME:,} shares (20d avg)",
        }
    )
    if not liquidity_ok:
        return _fail(checks, "low_liquidity")

    return {"passed": True, "fail_reason": None, "checks": checks}


def check_launchpad_eligibility(df: pd.DataFrame) -> tuple[bool, str]:
    detail = launchpad_eligibility_detail(df)
    if detail["passed"]:
        return True, "eligible"
    return False, detail["fail_reason"] or "unknown"


def _crossed_above_zero(series: pd.Series, *, within_bars: int) -> bool:
    """True when the series crossed from <=0 to >0 on any of the last `within_bars` bars."""
    if len(series) < 2 or pd.isna(series.iloc[-1]):
        return False
    segment = series.iloc[-(within_bars + 1) :]
    vals = segment.to_numpy(dtype=float)
    start = max(1, len(vals) - within_bars)
    for i in range(start, len(vals)):
        if vals[i] > 0 and vals[i - 1] <= 0:
            return True
    return False


def score_macd_zero_line_from_series(
    line: pd.Series,
    signal: pd.Series,
    *,
    lookback: int = LAUNCHPAD_MACD_ZERO_CROSS_LOOKBACK,
) -> tuple[float, dict]:
    """MACD Zero-Line Acceleration (max 25 pts) from precomputed MACD series."""
    if len(line) < lookback + 1 or pd.isna(line.iloc[-1]) or pd.isna(signal.iloc[-1]):
        return 0.0, {}

    macd_today = float(line.iloc[-1])
    signal_today = float(signal.iloc[-1])
    details = {
        "macd_line": round(macd_today, 4),
        "macd_signal": round(signal_today, 4),
    }

    if macd_today <= signal_today:
        return 0.0, details

    if macd_today > 0 and signal_today > 0:
        macd_crossed = _crossed_above_zero(line, within_bars=lookback)
        signal_crossed = _crossed_above_zero(signal, within_bars=lookback)
        details["macd_zero_cross"] = macd_crossed
        details["signal_zero_cross"] = signal_crossed
        if macd_crossed and signal_crossed:
            return 25.0, {**details, "phase": "zero_line_ignition"}
        return 0.0, {**details, "phase": "above_zero_established"}

    if macd_today < 0 and signal_today < 0:
        return 15.0, {**details, "phase": "early_recovery"}

    return 0.0, details


def score_macd_zero_line(df: pd.DataFrame) -> tuple[float, dict]:
    """MACD Zero-Line Acceleration (max 25 pts)."""
    close = df["Close"]
    line = macd_line(close)
    signal = macd_signal(close)
    return score_macd_zero_line_from_series(line, signal)


def score_ma_tightness(df: pd.DataFrame) -> tuple[float, dict]:
    """Multi-MA Tightness Squeeze (max 25 pts)."""
    close = df["Close"]
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    s50 = float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else None
    s200 = float(sma200.iloc[-1]) if not pd.isna(sma200.iloc[-1]) else None
    if s50 is None or s200 is None or s200 == 0:
        return 0.0, {}

    spread = (max(s50, s200) - min(s50, s200)) / s200
    details = {
        "sma50": round(s50, 2),
        "sma200": round(s200, 2),
        "ma_spread_pct": round(spread * 100, 2),
    }
    if spread <= 0.03:
        return 25.0, details
    if spread <= 0.06:
        return 15.0, details
    return 0.0, details


def score_atr_contraction(df: pd.DataFrame) -> tuple[float, dict]:
    """ATR Compression (max 20 pts): ATR(short) / ATR(long) volatility ratio.

    Proves the actual daily candles are contracting, not just the moving averages
    sitting close together. Lower ratio = tighter recent ranges vs the structural baseline.
    """
    if len(df) < LAUNCHPAD_ATR_LONG_WINDOW + 1:
        return 0.0, {}

    atr_short = atr(df, LAUNCHPAD_ATR_SHORT_WINDOW)
    atr_long = atr(df, LAUNCHPAD_ATR_LONG_WINDOW)
    short_val = float(atr_short.iloc[-1]) if not pd.isna(atr_short.iloc[-1]) else None
    long_val = float(atr_long.iloc[-1]) if not pd.isna(atr_long.iloc[-1]) else None
    if short_val is None or long_val is None or long_val == 0:
        return 0.0, {}

    ratio = short_val / long_val
    details = {
        "atr_short": round(short_val, 4),
        "atr_long": round(long_val, 4),
        "volatility_ratio": round(ratio, 4),
    }
    if ratio < LAUNCHPAD_ATR_RATIO_STRONG:
        return 20.0, details
    if ratio < LAUNCHPAD_ATR_RATIO_OK:
        return 12.0, details
    return 0.0, details


def score_volume_dry_up(df: pd.DataFrame) -> tuple[float, dict]:
    """Volume Dry-Up (max 15 pts): mean(vol short) / SMA(vol long).

    A coiled spring is defined by the evaporation of selling pressure right before
    the launch. Reward stocks where recent volume drops well below the baseline.
    """
    long_window = LAUNCHPAD_VOLUME_DRYUP_LONG_WINDOW
    short_window = LAUNCHPAD_VOLUME_DRYUP_SHORT_WINDOW
    if len(df) < long_window:
        return 0.0, {}

    volume = df["Volume"]
    baseline = float(volume.tail(long_window).mean())
    if baseline == 0:
        return 0.0, {}
    recent = float(volume.tail(short_window).mean())
    ratio = recent / baseline
    details = {
        "recent_volume": int(recent),
        "baseline_volume": int(baseline),
        "volume_dry_up_ratio": round(ratio, 4),
    }
    if ratio <= LAUNCHPAD_VOLUME_DRYUP_STRONG:
        return 15.0, details
    if ratio <= LAUNCHPAD_VOLUME_DRYUP_OK:
        return 10.0, details
    return 0.0, details


def _dedupe_swing_lows(
    swings: list[tuple[int, float]],
    *,
    min_gap: int = LAUNCHPAD_SWING_DEDUPE_MIN_GAP,
) -> list[tuple[int, float]]:
    """Collapse adjacent swing detections into one structural low per pivot."""
    if not swings:
        return []
    deduped = [swings[0]]
    for idx, price in swings[1:]:
        last_idx, last_price = deduped[-1]
        if idx - last_idx < min_gap:
            if price <= last_price:
                deduped[-1] = (idx, price)
        else:
            deduped.append((idx, price))
    return deduped


def _dedupe_swing_highs(
    swings: list[tuple[int, float]],
    *,
    min_gap: int = LAUNCHPAD_SWING_DEDUPE_MIN_GAP,
) -> list[tuple[int, float]]:
    """Collapse adjacent swing detections into one structural high per pivot."""
    if not swings:
        return []
    deduped = [swings[0]]
    for idx, price in swings[1:]:
        last_idx, last_price = deduped[-1]
        if idx - last_idx < min_gap:
            if price >= last_price:
                deduped[-1] = (idx, price)
        else:
            deduped.append((idx, price))
    return deduped


def _pullback_legs(
    highs: list[tuple[int, float]],
    lows: list[tuple[int, float]],
) -> list[dict]:
    """Pair each swing high with the next swing low to form pullback legs.

    Returns legs ordered by their swing-low index, each with the peak, trough,
    and fractional pullback depth ``(high - low) / high``.
    """
    legs: list[dict] = []
    for high_idx, high_price in highs:
        if high_price <= 0:
            continue
        following = [(idx, price) for idx, price in lows if idx > high_idx]
        if not following:
            continue
        low_idx, low_price = following[0]
        depth = (high_price - low_price) / high_price
        if depth <= 0:
            continue
        legs.append(
            {
                "high_idx": high_idx,
                "high": high_price,
                "low_idx": low_idx,
                "low": low_price,
                "depth": depth,
            }
        )
    legs.sort(key=lambda leg: leg["low_idx"])
    return legs


def score_swing_low_vcp(
    df: pd.DataFrame,
    *,
    history_days: int = LAUNCHPAD_SWING_HISTORY_DAYS,
) -> tuple[float, dict]:
    """Volatility Contraction Pattern (max 15 pts).

    Compares the depth of the latest structural pullback (swing high -> swing low)
    against the prior pullback. Successively shallower pullbacks are the signature
    of institutions stepping in higher to absorb overhead supply.
    """
    if len(df) < 10:
        return 0.0, {}

    history = df.tail(history_days)
    history_start = len(df) - len(history)
    highs = [
        (history_start + idx, price)
        for idx, price in _dedupe_swing_highs(find_swing_highs(history["High"], order=2))
    ]
    lows = [
        (history_start + idx, price)
        for idx, price in _dedupe_swing_lows(find_swing_lows(history["Low"], order=2))
    ]

    legs = _pullback_legs(highs, lows)
    details: dict = {"pullback_leg_count": len(legs)}
    if len(legs) < 2:
        return 0.0, details

    prior_leg = legs[-2]
    latest_leg = legs[-1]
    prior_depth = prior_leg["depth"]
    latest_depth = latest_leg["depth"]
    details["prior_pullback_pct"] = round(prior_depth * 100, 2)
    details["latest_pullback_pct"] = round(latest_depth * 100, 2)
    if prior_depth <= 0:
        return 0.0, details

    depth_ratio = latest_depth / prior_depth
    details["contraction_ratio"] = round(depth_ratio, 4)
    if depth_ratio <= LAUNCHPAD_VCP_RATIO_STRONG:
        return 15.0, details
    if depth_ratio <= LAUNCHPAD_VCP_RATIO_OK:
        return 8.0, details
    return 0.0, details


def _fail(checks: list[dict], reason: str) -> dict:
    return {"passed": False, "fail_reason": reason, "checks": checks}
