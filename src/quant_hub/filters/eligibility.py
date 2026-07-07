import pandas as pd

from quant_hub.config import (
    BREAKOUT_MAX_PCT_BELOW_52W_HIGH,
    BREAKOUT_MIN_PCT_ABOVE_52W_LOW,
    BREAKOUT_REQUIRE_SMA200_RISING,
    ETF_MIN_AVG_VOLUME,
    ETF_MIN_PRICE,
    ETF_MIN_TRADING_DAYS,
    LOOKBACK_DAYS,
    MIN_AVG_VOLUME,
    MIN_PRICE,
    MIN_TRADING_DAYS,
)
from quant_hub.data.quality import has_price_spike, price_spike_ratio
from quant_hub.indicators import pct_above_low, range_52w, sma

FILTER_LABELS = {
    "insufficient_history": "Fewer than 200 trading days of history",
    "insufficient_etf_history": "Fewer than 120 trading days of history (ETF mode)",
    "price_below_minimum": "Price below $10 minimum",
    "etf_price_below_minimum": "Price below ETF minimum ($5)",
    "low_liquidity": "20-day average volume below 750,000 shares",
    "etf_low_liquidity": "20-day average volume below 500,000 shares (ETF mode)",
    "insufficient_ma_history": "Not enough data to compute moving averages",
    "trend_misaligned": "Price not above 200-day moving average",
    "sma200_not_rising": "200-day MA is not rising vs 30 trading days ago",
    "too_close_to_52w_low": f"Price less than {BREAKOUT_MIN_PCT_ABOVE_52W_LOW:.0%} above 52-week low",
    "too_far_from_52w_high": (
        f"Price more than {BREAKOUT_MAX_PCT_BELOW_52W_HIGH:.0%} below 52-week high"
    ),
    "no_price_data": "No price data available",
    "price_data_anomaly": "Latest price deviates sharply from recent history (possible bad feed)",
    "eligible": "Passed all eligibility filters",
}


def eligibility_detail(df: pd.DataFrame, *, mode: str = "stock") -> dict:
    """Return structured eligibility checks. Use mode='etf' for ETF-only universes."""
    if mode == "etf":
        return _etf_eligibility_detail(df)
    return _stock_eligibility_detail(df)


def _etf_eligibility_detail(df: pd.DataFrame) -> dict:
    """Relaxed gates for sector/commodity ETFs — no Stage-2 MA stack or 52w position rules."""
    checks: list[dict] = []

    history_len = len(df)
    checks.append(
        {
            "rule": "trading_history",
            "passed": history_len >= ETF_MIN_TRADING_DAYS,
            "value": history_len,
            "threshold": f">= {ETF_MIN_TRADING_DAYS} days",
        }
    )
    if history_len < ETF_MIN_TRADING_DAYS:
        return _fail(checks, "insufficient_etf_history")

    close = df["Close"]
    price = float(close.iloc[-1])
    checks.append(
        {
            "rule": "price",
            "passed": price >= ETF_MIN_PRICE,
            "value": round(price, 2),
            "threshold": f">= ${ETF_MIN_PRICE:.0f}",
        }
    )
    if price < ETF_MIN_PRICE:
        return _fail(checks, "etf_price_below_minimum")

    spike_ratio = price_spike_ratio(df)
    spike = has_price_spike(df)
    checks.append(
        {
            "rule": "price_stability",
            "passed": not spike,
            "value": round(spike_ratio, 2) if spike_ratio is not None else None,
            "threshold": "latest close within 3x of 20-day median",
        }
    )
    if spike:
        return _fail(checks, "price_data_anomaly")

    avg_vol = float(df["Volume"].tail(20).mean())
    checks.append(
        {
            "rule": "liquidity",
            "passed": avg_vol >= ETF_MIN_AVG_VOLUME,
            "value": int(avg_vol),
            "threshold": f">= {ETF_MIN_AVG_VOLUME:,} shares (20d avg)",
        }
    )
    if avg_vol < ETF_MIN_AVG_VOLUME:
        return _fail(checks, "etf_low_liquidity")

    return {"passed": True, "fail_reason": None, "checks": checks}


def _stock_eligibility_detail(df: pd.DataFrame) -> dict:
    """Return structured eligibility checks with actual values."""
    checks: list[dict] = []

    history_len = len(df)
    checks.append(
        {
            "rule": "trading_history",
            "passed": history_len >= MIN_TRADING_DAYS,
            "value": history_len,
            "threshold": f">= {MIN_TRADING_DAYS} days",
        }
    )
    if history_len < MIN_TRADING_DAYS:
        return _fail(checks, "insufficient_history")

    close = df["Close"]
    price = float(close.iloc[-1])
    checks.append(
        {
            "rule": "price",
            "passed": price >= MIN_PRICE,
            "value": round(price, 2),
            "threshold": f">= ${MIN_PRICE:.0f}",
        }
    )
    if price < MIN_PRICE:
        return _fail(checks, "price_below_minimum")

    spike_ratio = price_spike_ratio(df)
    spike = has_price_spike(df)
    checks.append(
        {
            "rule": "price_stability",
            "passed": not spike,
            "value": round(spike_ratio, 2) if spike_ratio is not None else None,
            "threshold": "latest close within 3x of 20-day median",
        }
    )
    if spike:
        return _fail(checks, "price_data_anomaly")

    avg_vol = float(df["Volume"].tail(20).mean())
    checks.append(
        {
            "rule": "liquidity",
            "passed": avg_vol >= MIN_AVG_VOLUME,
            "value": int(avg_vol),
            "threshold": f">= {MIN_AVG_VOLUME:,} shares (20d avg)",
        }
    )
    if avg_vol < MIN_AVG_VOLUME:
        return _fail(checks, "low_liquidity")

    sma50 = sma(close, 50)
    sma150 = sma(close, 150)
    sma200 = sma(close, 200)
    s50 = float(sma50.iloc[-1]) if not pd.isna(sma50.iloc[-1]) else None
    s150 = float(sma150.iloc[-1]) if not pd.isna(sma150.iloc[-1]) else None
    s200 = float(sma200.iloc[-1]) if not pd.isna(sma200.iloc[-1]) else None

    if s50 is None or s150 is None or s200 is None:
        checks.append(
            {
                "rule": "moving_averages",
                "passed": False,
                "value": None,
                "threshold": "SMA50/150/200 computable",
            }
        )
        return _fail(checks, "insufficient_ma_history")

    trend_ok = price > s200
    checks.append(
        {
            "rule": "trend_alignment",
            "passed": trend_ok,
            "value": {
                "price": round(price, 2),
                "sma50": round(s50, 2),
                "sma150": round(s150, 2),
                "sma200": round(s200, 2),
            },
            "threshold": "price > SMA200",
            "detail": _trend_detail(price, s50, s150, s200),
        }
    )
    if not trend_ok:
        return _fail(checks, "trend_misaligned")

    sma200_rising = len(sma200) >= 31 and float(sma200.iloc[-1]) > float(sma200.iloc[-31])
    checks.append(
        {
            "rule": "sma200_rising",
            "passed": sma200_rising,
            "value": {
                "sma200_today": round(float(sma200.iloc[-1]), 2),
                "sma200_30d_ago": round(float(sma200.iloc[-31]), 2),
            },
            "threshold": "SMA200 today > SMA200 30 trading days ago (informational)",
            "required": BREAKOUT_REQUIRE_SMA200_RISING,
        }
    )
    if BREAKOUT_REQUIRE_SMA200_RISING and not sma200_rising:
        return _fail(checks, "sma200_not_rising")

    high_52w, low_52w = range_52w(df, LOOKBACK_DAYS)
    above_low = pct_above_low(price, low_52w)
    below_high = (high_52w - price) / high_52w if high_52w else None
    above_ok = above_low is not None and above_low >= BREAKOUT_MIN_PCT_ABOVE_52W_LOW
    below_ok = below_high is not None and below_high <= BREAKOUT_MAX_PCT_BELOW_52W_HIGH

    checks.append(
        {
            "rule": "52w_position",
            "passed": above_ok and below_ok,
            "value": {
                "high_52w": round(high_52w, 2),
                "low_52w": round(low_52w, 2),
                "pct_above_low": round(above_low * 100, 1) if above_low else None,
                "pct_below_high": round(below_high * 100, 1) if below_high else None,
            },
            "threshold": (
                f">= {BREAKOUT_MIN_PCT_ABOVE_52W_LOW:.0%} above 52w low AND "
                f"<= {BREAKOUT_MAX_PCT_BELOW_52W_HIGH:.0%} below 52w high"
            ),
        }
    )
    if not above_ok:
        return _fail(checks, "too_close_to_52w_low")
    if not below_ok:
        return _fail(checks, "too_far_from_52w_high")

    return {"passed": True, "fail_reason": None, "checks": checks}


def check_eligibility(df: pd.DataFrame, *, mode: str = "stock") -> tuple[bool, str]:
    """Apply hard eligibility filters. Returns (eligible, reason)."""
    detail = eligibility_detail(df, mode=mode)
    if detail["passed"]:
        return True, "eligible"
    return False, detail["fail_reason"]


def _fail(checks: list[dict], reason: str) -> dict:
    return {"passed": False, "fail_reason": reason, "checks": checks}


def _trend_detail(price: float, s50: float, s150: float, s200: float) -> str:
    if price <= s200:
        return f"price {price:.2f} <= SMA200 {s200:.2f}"
    notes: list[str] = []
    if price <= s50:
        notes.append(f"below SMA50 {s50:.2f} (short-term pullback OK)")
    if s50 <= s200:
        notes.append(f"SMA50 {s50:.2f} <= SMA200 {s200:.2f} (early turn OK)")
    elif s50 <= s150:
        notes.append(f"SMA150 {s150:.2f} not yet stacked (early-base OK)")
    if notes:
        return "; ".join(notes)
    return "above SMA200 with constructive MA structure"
