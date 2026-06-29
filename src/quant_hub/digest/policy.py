"""Digest quality thresholds — aligned with scanner tier logic."""

from __future__ import annotations

# Universes
DAILY_BREAKOUT_UNIVERSE = "sp500"
WEEKLY_SWING_UNIVERSE = "sp500"
WEEKLY_LYNCH_UNIVERSE = "sp500"
WEEKLY_ETF_UNIVERSE = "sector_commodity_etfs"

# Breakout (matches strategies/breakout/tiers.py)
BREAKOUT_TIER1 = "Tier 1"
BREAKOUT_TIER2 = "Tier 2"
BREAKOUT_ACTIONABLE = (BREAKOUT_TIER1, BREAKOUT_TIER2)

# Daily caps
DAILY_TIER1_MAX = 15
DAILY_TIER2_MAX = 10
DAILY_SEND_WHEN_EMPTY = True

# Weekly caps
WEEKLY_SWING_MIN_SCORE = 70.0  # A/B band (scoring.py)
WEEKLY_LYNCH_TOP_N = 15
WEEKLY_TABLE_MAX = 15

# Convergence
WEEKLY_TRIPLE_BREAKOUT_TIERS = (BREAKOUT_TIER1,)
WEEKLY_DOUBLE_BREAKOUT_TIERS = BREAKOUT_ACTIONABLE

# Persistence (weekday breakout runs)
PERSISTENCE_MIN_DAYS = 3
PERSISTENCE_LOOKBACK_DAYS = 5

# Readiness
DAILY_SCAN_MAX_AGE_HOURS = 3
WEEKLY_SWING_MAX_AGE_DAYS = 4
WEEKLY_LYNCH_MAX_AGE_DAYS = 2

# Regime
WEAK_REGIME_LABEL = "weak"

DIGEST_POLICY_FOOTER = (
    "Tier 1: norm≥80, final≥70, compression≥8, volume signal met. "
    "Tier 2: norm≥65. Swing highlights: quality score≥70 (A/B)."
)
