"""Mean reversion rubric v2.2 constants."""

from __future__ import annotations

from quant_hub.config import (
    MEAN_REVERSION_HIGH_CONVICTION,
    MEAN_REVERSION_WATCHLIST,
)

MACRO_TREND_POINTS = 20
PRICE_EXTENSION_POINTS = 30
RSI_HOOK_POINTS = 25
VOLUME_POINTS = 10
SECTOR_ROTATION_POINTS = 8
VOLATILITY_POINTS = 7
MAX_SCORE = 100

TIER_HIGH_CONVICTION = "HIGH_CONVICTION"
TIER_WATCHLIST = "WATCHLIST"
TIER_FILTERED = "filtered"

SIGNAL_STRONG_LONG = "Strong Long"
SIGNAL_STRONG_SHORT = "Strong Short"
SIGNAL_MARGINAL = "Marginal"
SIGNAL_NO_TRADE = "No Trade"

SETUP_LONG = "SETUP_LONG"
SETUP_SHORT = "SETUP_SHORT"

BENCHMARK_SYMBOLS = frozenset({"QQQ", "SPY"})
DEFENSIVE_SECTORS = frozenset({"XLP", "XLU", "XLV"})
ENERGY_SECTORS = frozenset({"XLE"})

MEAN_REVERSION_RUBRIC: tuple[tuple[str, str], ...] = (
    ("Macro Trend", "Price vs 500 EMA — full credit when on the correct side of macro trend."),
    ("Price Extension", "Proximity to lower BB (long) or upper BB (short)."),
    (
        "RSI Momentum Hook",
        "At band + RSI hook: cross from oversold/overbought or rising hook forming.",
    ),
    ("Volume Confirmation", "Relative volume vs 20-day average on signal day."),
    ("Sector Rotation", "RS vs SPY (ETFs) or vs sector ETF (stocks) — universe percentile."),
    ("Volatility Regime", "BB width not dead — elevated vol supports mean reversion."),
)

FILTER_LABELS = {
    "insufficient_data": "Fewer than required daily bars for 500 EMA",
    "no_price_data": "No daily OHLCV data",
    "invalid_ohlcv": "OHLCV failed validation",
    "scan_error": "Scanner error during evaluation",
    "stale_ohlcv": "Daily bars are stale",
}

HIGH_CONVICTION_THRESHOLD = MEAN_REVERSION_HIGH_CONVICTION
WATCHLIST_THRESHOLD = MEAN_REVERSION_WATCHLIST
