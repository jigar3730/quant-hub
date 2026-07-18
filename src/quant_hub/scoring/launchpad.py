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
    bollinger_bands,
    ema,
    find_swing_highs,
    find_swing_lows,
    macd_line,
    macd_signal,
    sma,
)

FILTER_LABELS = {
    "insufficient_history": f"Fewer than {LAUNCHPAD_MIN_HISTORY_DAYS} trading days of history",
    "no_price_data": "No price data available",
    "price_below_10": "Current close below $10.00",
    "volume_below_min": "30-day average volume below 500,000 shares",
    "macro_trend_not_aligned": "Price not above the 200-day EMA",
    "structural_proximity": "Price not within 2.5% of the rising 50-day EMA or 2.0% of a support shelf",
    "eligible": "Passed all eligibility filters",
}


def launchpad_eligibility_detail(df: pd.DataFrame) -> dict:
    """Return structured eligibility checks for the coiled-spring launchpad rubric."""
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
    if price < 10.0:
        checks.append(
            {
                "rule": "price_minimum",
                "passed": False,
                "value": round(price, 2),
                "threshold": ">= 10.00",
            }
        )
        return _fail(checks, "price_below_10")
    checks.append(
        {
            "rule": "price_minimum",
            "passed": True,
            "value": round(price, 2),
            "threshold": ">= 10.00",
        }
    )

    avg_vol_30d = float(df["Volume"].tail(30).mean())
    liquidity_ok = avg_vol_30d >= 500_000
    checks.append(
        {
            "rule": "volume_minimum",
            "passed": liquidity_ok,
            "value": int(avg_vol_30d),
            "threshold": ">= 500,000 shares (30d avg)",
        }
    )
    if not liquidity_ok:
        return _fail(checks, "volume_below_min")

    ema200 = ema(close, 200)
    ema200_val = float(ema200.iloc[-1]) if not pd.isna(ema200.iloc[-1]) else None
    macro_ok = ema200_val is not None and price > ema200_val
    checks.append(
        {
            "rule": "macro_trend_alignment",
            "passed": macro_ok,
            "value": {"price": round(price, 2), "ema200": round(ema200_val, 2) if ema200_val is not None else None},
            "threshold": "price > 200-day EMA",
        }
    )
    if not macro_ok:
        return _fail(checks, "macro_trend_not_aligned")

    ema50 = ema(close, 50)
    ema50_val = float(ema50.iloc[-1]) if not pd.isna(ema50.iloc[-1]) else None
    support_ok = False
    if ema50_val is not None:
        support_ok = abs(price - ema50_val) / ema50_val <= 0.025
    if not support_ok:
        support_ok = _near_support_shelf(close)
    checks.append(
        {
            "rule": "structural_proximity",
            "passed": support_ok,
            "value": {
                "price": round(price, 2),
                "ema50": round(ema50_val, 2) if ema50_val is not None else None,
            },
            "threshold": "within +/-2.5% of 50-day EMA or +/-2.0% of support shelf",
        }
    )
    if not support_ok:
        return _fail(checks, "structural_proximity")

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


def score_squeeze_intensity(df: pd.DataFrame) -> tuple[float, dict]:
    """Volatility compression score (max 40 pts)."""
    close = df["Close"]
    if len(close) < 20:
        return 0.0, {}

    upper_bb, _, lower_bb = bollinger_bands(close, window=20, num_std=2.0)
    ema20 = ema(close, 20)
    atr20 = atr(df, 20)
    upper_kc = ema20 + 1.5 * atr20
    lower_kc = ema20 - 1.5 * atr20
    bb_width = upper_bb - lower_bb
    kc_width = upper_kc - lower_kc
    squeeze_ratio = float(bb_width.iloc[-1] / kc_width.iloc[-1]) if kc_width.iloc[-1] else None
    details = {
        "squeeze_ratio": round(squeeze_ratio, 4) if squeeze_ratio is not None else None,
        "squeeze_active": squeeze_ratio is not None and squeeze_ratio < 1.0,
    }
    if squeeze_ratio is None:
        return 0.0, details
    if squeeze_ratio < 0.90:
        return 40.0, details
    if squeeze_ratio <= 1.00:
        return 25.0, details
    return 0.0, details


def score_tightness_percentile(df: pd.DataFrame) -> tuple[float, dict]:
    """Daily candle tightness percentile score (max 15 pts)."""
    if len(df) < 60:
        return 0.0, {}

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    tr = pd.concat(
        [(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    atr3 = tr.rolling(3, min_periods=3).mean()
    tightness = atr3 / close
    recent = float(tightness.iloc[-1]) if not pd.isna(tightness.iloc[-1]) else None
    if recent is None:
        return 0.0, {}
    hist = tightness.dropna().tail(60)
    if hist.empty:
        return 0.0, {}
    percentile = float((hist <= recent).mean())
    details = {
        "tightness_score": round(recent, 6),
        "tightness_rank_pct": round(percentile, 4),
    }
    if percentile <= 0.10:
        return 15.0, details
    return 0.0, details


def score_volume_vacuum_depth(df: pd.DataFrame) -> tuple[float, dict]:
    """Volume vacuum depth score (max 30 pts)."""
    if len(df) < 50:
        return 0.0, {}

    volume = df["Volume"]
    avg_vol_50 = float(volume.tail(50).mean())
    current_vol = float(volume.iloc[-1])
    if avg_vol_50 <= 0:
        return 0.0, {}
    rvol = current_vol / avg_vol_50
    details = {
        "current_volume": int(current_vol),
        "avg_volume_50": int(avg_vol_50),
        "rvol": round(rvol, 4),
    }
    if rvol <= 0.45:
        return 30.0, details
    if rvol <= 0.60:
        return 15.0, details
    return 0.0, details


def score_trend_proximity_match(price_df: pd.DataFrame, spy_df: pd.DataFrame) -> tuple[float, dict]:
    """Trend + structural proximity score (max 15 pts)."""
    if price_df is None or spy_df is None or price_df.empty or spy_df.empty:
        return 0.0, {}

    price_close = price_df["Close"]
    spy_close = spy_df["Close"]
    price_ema50 = ema(price_close, 50)
    price_ema200 = ema(price_close, 200)
    spy_ema50 = ema(spy_close, 50)
    spy_ema200 = ema(spy_close, 200)
    price = float(price_close.iloc[-1])
    price_ema50_val = float(price_ema50.iloc[-1]) if not pd.isna(price_ema50.iloc[-1]) else None
    price_ema200_val = float(price_ema200.iloc[-1]) if not pd.isna(price_ema200.iloc[-1]) else None
    spy_close_val = float(spy_close.iloc[-1]) if not pd.isna(spy_close.iloc[-1]) else None
    spy_ema50_val = float(spy_ema50.iloc[-1]) if not pd.isna(spy_ema50.iloc[-1]) else None
    spy_ema200_val = float(spy_ema200.iloc[-1]) if not pd.isna(spy_ema200.iloc[-1]) else None
    relative_strength_positive = (
        price_ema50_val is not None
        and spy_ema50_val is not None
        and price_ema50_val > spy_ema50_val
    )
    near_support = False
    if price_ema50_val is not None:
        near_support = abs(price - price_ema50_val) / price_ema50_val <= 0.015
    details = {
        "relative_strength_positive": relative_strength_positive,
        "near_support": near_support,
        "price": round(price, 2),
        "spy_close": round(spy_close_val, 2) if spy_close_val is not None else None,
        "price_ema50": round(price_ema50_val, 2) if price_ema50_val is not None else None,
        "spy_ema50": round(spy_ema50_val, 2) if spy_ema50_val is not None else None,
        "price_ema200": round(price_ema200_val, 2) if price_ema200_val is not None else None,
        "spy_ema200": round(spy_ema200_val, 2) if spy_ema200_val is not None else None,
    }
    if relative_strength_positive and near_support:
        return 15.0, details
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


def _near_support_shelf(close: pd.Series, *, tolerance: float = 0.02) -> bool:
    if len(close) < 2:
        return False
    recent = close.tail(60)
    if recent.empty:
        return False
    support = float(recent.min())
    if support <= 0:
        return False
    price = float(close.iloc[-1])
    return abs(price - support) / support <= tolerance


def _fail(checks: list[dict], reason: str) -> dict:
    return {"passed": False, "fail_reason": reason, "checks": checks}


# Backward-compatible wrappers for older launchpad codepaths.
def score_ma_tightness(df: pd.DataFrame) -> tuple[float, dict]:
    return score_squeeze_intensity(df)


def score_atr_contraction(df: pd.DataFrame) -> tuple[float, dict]:
    return score_tightness_percentile(df)


def score_volume_dry_up(df: pd.DataFrame) -> tuple[float, dict]:
    return score_volume_vacuum_depth(df)


def score_swing_low_vcp(df: pd.DataFrame, *, history_days: int = LAUNCHPAD_SWING_HISTORY_DAYS) -> tuple[float, dict]:
    _ = history_days
    return score_trend_proximity_match(df, df)
