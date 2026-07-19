"""Launchpad dashboard score guide."""

from __future__ import annotations

import streamlit as st

LAUNCHPAD_COMPONENT_HELP = {
    "macd_zero_line": "MACD line crossing above zero with signal confirmation (Tier-1 gate).",
    "squeeze_intensity": "Bollinger vs Keltner squeeze — volatility compression.",
    "tightness_percentile": "Recent candle range tightness vs the prior 60 bars.",
    "volume_vacuum_depth": "Current volume vs the 50-day baseline — supply exhaustion.",
    "trend_proximity_match": "Partial credit: RS vs SPY (8) + near EMA50/ATR/shelf (4–7).",
}

LAUNCHPAD_COMPONENT_SUMMARY = {
    "macd_zero_line": "Momentum ignition at the zero line.",
    "squeeze_intensity": "Volatility coil before expansion.",
    "tightness_percentile": "Daily candle range squeeze.",
    "volume_vacuum_depth": "Absolute liquidity/supply exhaustion.",
    "trend_proximity_match": "Relative strength + proximity to support.",
}


def render_launchpad_score_guide(*, in_sidebar: bool = False) -> None:
    target = st.sidebar if in_sidebar else st
    target.markdown("#### Launchpad Rubric")
    target.markdown(
        """
| Eligibility | Condition |
|-------------|-----------|
| History | ≥ 200 trading days |
| Price / liquidity | Close ≥ $10 · 30d avg vol ≥ 750,000 |
| Macro trend | Price > EMA200 |
| Proximity | Within 5% of EMA50, 1.0×ATR(14), or 2% of support shelf |

**Scoring (raw max 100):**
- Squeeze Intensity (40) · Tightness (15) · Volume Vacuum (30)
- Trend & Proximity (15): RS vs SPY 0/8 + near support 0/4/7
- MACD Zero-Line (gate only): ignition 25 → Tier 1 with norm ≥80

**Tiers:** Tier 1 = norm ≥80 + MACD=25 · Tier 2 = norm ≥65
        """
    )
