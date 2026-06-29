"""Swing scanner thresholds — shared by gate checks and quality scoring."""

from __future__ import annotations

# Pullback zone: close within EMA20 ± ATR multiples (weekly bars)
PULLBACK_ATR_BELOW = 0.25  # allow modest pierce below EMA20 on long
PULLBACK_ATR_ABOVE = 1.0  # allow up to 1 ATR above EMA20 on long pullback

# Quality score component caps (base max = 100)
SWING_CORE_RULE_POINTS = 16  # 5 setup rules × 16 = 80
SWING_RS_POINTS = 10
SWING_VOLUME_POINTS = 10
SWING_MAX_BASE = 100
SWING_RULE_COUNT = 5

# Weekly RS vs SPY lookbacks (in weeks)
RS_WEEK_LOOKBACKS = (13, 26)

# Volume: pullback week vs prior N-week average (excl. current)
VOLUME_LOOKBACK_WEEKS = 10

# Chase penalty: beyond pullback zone by this many ATR
CHASE_ATR_THRESHOLD = 0.5
