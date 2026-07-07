"""Launchpad Reversal dashboard score guide."""

from __future__ import annotations

import streamlit as st

LAUNCHPAD_COMPONENT_HELP = {
    "ma_tightness": "How tightly SMA50 and SMA200 are coiled together.",
    "macd_zero_line": "MACD line crossing above zero with signal confirmation.",
    "atr_contraction": "Short-term ATR vs long-term ATR — proves daily ranges are shrinking.",
    "volume_dry_up": "Recent 3-day volume vs the 50-day baseline — supply exhaustion.",
    "swing_low_vcp": "Latest pullback depth vs the prior pullback (contraction pattern).",
}

LAUNCHPAD_COMPONENT_SUMMARY = {
    "ma_tightness": "Multi-MA compression before expansion.",
    "macd_zero_line": "Momentum ignition at the zero line.",
    "atr_contraction": "Daily candle range squeeze.",
    "volume_dry_up": "Absolute liquidity/supply exhaustion.",
    "swing_low_vcp": "Progressive higher-low wave structure (VCP).",
}


def render_launchpad_score_guide(*, in_sidebar: bool = False) -> None:
    target = st.sidebar if in_sidebar else st
    target.markdown("#### Launchpad Reversal Rubric")
    target.markdown(
        """
| Eligibility | Condition |
|-------------|-----------|
| Base clearance | Price > SMA50 AND Price > SMA200 |
| Fresh trend | SMA50 > SMA50 (10 days ago) |
| Not extended | Price ≤ 8% above 20-day median close |
| Liquidity | 20-day avg volume ≥ 750,000 |

**Scoring (raw max 100) — the Coiled Spring engine:**
- MA Tightness (25): SMA50/200 spread ≤3% → 25 · ≤6% → 15
- MACD Zero-Line (25): zero-line ignition → 25 · early recovery → 15
- ATR Contraction (20): ATR(14)/ATR(50) < 0.70 → 20 · < 0.80 → 12
- Volume Dry-Up (15): 3d/50d volume ≤0.50 → 15 · ≤0.60 → 10
- Swing-Low VCP (15): latest pullback ≤50% of prior → 15 · ≤75% → 8

**Tiers:** Tier 1 = norm ≥80 + MACD=25 · Tier 2 = norm ≥65
        """
    )
