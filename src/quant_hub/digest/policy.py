"""Launchpad and Lynch digest policy."""

from __future__ import annotations

from quant_hub.config import PRIMARY_INDEX_UNIVERSE

# Universes and strategies
DAILY_LAUNCHPAD_UNIVERSE = PRIMARY_INDEX_UNIVERSE
WEEKLY_LYNCH_UNIVERSE = PRIMARY_INDEX_UNIVERSE
WEEKLY_LAUNCHPAD_UNIVERSE = PRIMARY_INDEX_UNIVERSE
LAUNCHPAD_STRATEGY = "launchpad"
LYNCH_STRATEGY = "lynch"

# Launchpad actionable tiers (matches strategies/launchpad/tiers.py).
LAUNCHPAD_TIER1 = "Tier 1"
LAUNCHPAD_TIER2 = "Tier 2"
LAUNCHPAD_ACTIONABLE = (LAUNCHPAD_TIER1, LAUNCHPAD_TIER2)

# Daily caps
DAILY_TIER1_MAX = 15
DAILY_TIER2_MAX = 10
DAILY_SEND_WHEN_EMPTY = True

# Weekly caps
WEEKLY_LYNCH_TOP_N = 15

# Persistence (weekday Launchpad runs)
PERSISTENCE_MIN_DAYS = 3
PERSISTENCE_LOOKBACK_DAYS = 5

# Readiness
DAILY_SCAN_MAX_AGE_HOURS = 3
WEEKLY_LAUNCHPAD_MAX_AGE_DAYS = 7

# Regime
WEAK_REGIME_LABEL = "weak"

DIGEST_POLICY_FOOTER = (
    "Launchpad Tier 1 requires a high normalized score and MACD zero-line ignition; "
    "Tier 2 is the qualified watchlist. Lynch candidates are ranked by Lynch score."
)
