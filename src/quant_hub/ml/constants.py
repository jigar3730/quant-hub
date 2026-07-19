"""ML schema versions and label definitions."""

from __future__ import annotations

from quant_hub.config import (
    DEFAULT_LABEL_HORIZONS,
    FEATURE_SCHEMA_VERSION,
    LABEL_RETURN_THRESHOLD_PCT,
)

LABEL_STATUS_OK = "ok"
LABEL_STATUS_NO_PRICE = "no_price"
LABEL_STATUS_INSUFFICIENT_FUTURE = "insufficient_future_bars"
LABEL_STATUS_INVALID_ANCHOR = "invalid_anchor"

# Launchpad: all eligible tiers are training candidates (filtered rows dropped when setups_only).
LAUNCHPAD_SETUP_TIERS = frozenset({"Tier 1", "Tier 2", "Tier 3"})

# Numeric features for launchpad LightGBM (mapped from scan payload `scores.*.raw`)
LAUNCHPAD_FEATURE_COLUMNS = (
    "final_score",
    "volatility_compression_ratio",
    "relative_strength_rank",
    "volume_rs_score",
    "resistance_distance_pct",
    "market_regime_multiplier",
)

MODEL_TYPE_LIGHTGBM_CLASSIFIER = "lightgbm_classifier"

__all__ = [
    "DEFAULT_LABEL_HORIZONS",
    "FEATURE_SCHEMA_VERSION",
    "LABEL_RETURN_THRESHOLD_PCT",
    "LABEL_STATUS_INSUFFICIENT_FUTURE",
    "LABEL_STATUS_INVALID_ANCHOR",
    "LABEL_STATUS_NO_PRICE",
    "LABEL_STATUS_OK",
    "LAUNCHPAD_FEATURE_COLUMNS",
    "LAUNCHPAD_SETUP_TIERS",
    "MODEL_TYPE_LIGHTGBM_CLASSIFIER",
]
