"""Swing setup scoring rubric for the dashboard."""

from __future__ import annotations

import streamlit as st

from quant_hub.strategies.swing.scoring import (
    SWING_MAX_PENALTY,
    SWING_PENALTY_RUBRIC,
    SWING_RULE_COUNT,
    SWING_RULE_POINTS,
    SWING_SCORE_RUBRIC,
)

SWING_GUIDE_TITLE = "Swing Setup Quality Rubric"
SWING_GUIDE_INTRO = (
    "Setup **quality score (0–100)** = **base** (partial credit on 5 rules) **− penalties**. "
    f"Each rule earns up to {SWING_RULE_POINTS} pts. Penalties are capped at −{SWING_MAX_PENALTY:.0f} total. "
    "**Setup gate** (SETUP_LONG/SHORT) still requires all 5 hard checks to pass."
)


def render_swing_score_guide(*, in_sidebar: bool = False) -> None:
    target = st.sidebar if in_sidebar else st
    target.markdown(f"##### {SWING_GUIDE_TITLE}")
    target.markdown(SWING_GUIDE_INTRO)

    target.markdown("**Base components (partial credit)**")
    for index, (name, detail) in enumerate(SWING_SCORE_RUBRIC, start=1):
        target.markdown(
            f"{index}. **{name}** — {detail} (0–{SWING_RULE_POINTS} pts)"
        )

    target.markdown("**Penalties (subtracted from base)**")
    for name, detail in SWING_PENALTY_RUBRIC:
        target.markdown(f"- **{name}** — {detail}")

    target.markdown("**Quality bands**")
    target.markdown(
        "- **A (85–100):** High quality — clean structure, minimal penalties\n"
        "- **B (70–84):** Valid setup — passes gate with minor flaws\n"
        "- **C (55–69):** Near-miss / soft — partial rules or moderate penalties\n"
        "- **D (<55):** Avoid — wrong structure or heavy penalties"
    )
    target.caption(
        f"Confirmed setups can score below 100 if chase, RSI stretch, or MACD overextension apply. "
        f"Near-misses spread across {SWING_RULE_COUNT * SWING_RULE_POINTS} base pts minus penalties."
    )
