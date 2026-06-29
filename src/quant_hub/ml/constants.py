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
    "revenue",
    "eps",
)

LABEL_STATUS_OK = "ok"
LABEL_STATUS_NO_PRICE = "no_price"
LABEL_STATUS_INSUFFICIENT_FUTURE = "insufficient_future_bars"
LABEL_STATUS_INVALID_ANCHOR = "invalid_anchor"

__all__ = [
    "BREAKOUT_SCORE_FACTORS",
    "DEFAULT_LABEL_HORIZONS",
    "FEATURE_SCHEMA_VERSION",
    "LABEL_RETURN_THRESHOLD_PCT",
    "LABEL_STATUS_INSUFFICIENT_FUTURE",
    "LABEL_STATUS_INVALID_ANCHOR",
    "LABEL_STATUS_NO_PRICE",
    "LABEL_STATUS_OK",
]
