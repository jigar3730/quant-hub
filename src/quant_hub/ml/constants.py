"""ML schema versions and label definitions."""

from __future__ import annotations

from quant_hub.config import (
    DEFAULT_LABEL_HORIZONS,
    FEATURE_SCHEMA_VERSION,
    LABEL_RETURN_THRESHOLD_PCT,
)

BREAKOUT_SCORE_FACTORS = (
    "rs_market",
    "rs_sector",
    "accumulation",
    "relative_volume",
    "compression",
    "pattern",
    "resistance",
)

LABEL_STATUS_OK = "ok"
LABEL_STATUS_NO_PRICE = "no_price"
LABEL_STATUS_INSUFFICIENT_FUTURE = "insufficient_future_bars"
LABEL_STATUS_INVALID_ANCHOR = "invalid_anchor"

SWING_SETUP_TIERS = frozenset({"SETUP_LONG", "SETUP_SHORT"})

# Numeric features for swing LightGBM (no labels, ids, or dates)
SWING_FEATURE_COLUMNS = (
    "swing_score",
    "rsi",
    "rs_ratio",
    "rs_percentile",
    "vol_ratio",
    "penalty_total",
    "checks_passed",
    "checks_total",
    "atr",
    "close",
    "regime_multiplier",
)

MODEL_TYPE_LIGHTGBM_CLASSIFIER = "lightgbm_classifier"

__all__ = [
    "BREAKOUT_SCORE_FACTORS",
    "DEFAULT_LABEL_HORIZONS",
    "FEATURE_SCHEMA_VERSION",
    "LABEL_RETURN_THRESHOLD_PCT",
    "LABEL_STATUS_INSUFFICIENT_FUTURE",
    "LABEL_STATUS_INVALID_ANCHOR",
    "LABEL_STATUS_NO_PRICE",
    "LABEL_STATUS_OK",
    "MODEL_TYPE_LIGHTGBM_CLASSIFIER",
    "SWING_FEATURE_COLUMNS",
    "SWING_SETUP_TIERS",
]
