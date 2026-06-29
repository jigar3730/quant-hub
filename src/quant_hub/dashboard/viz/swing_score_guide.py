"""Swing setup scoring rubric for the dashboard."""

from __future__ import annotations

import streamlit as st

from quant_hub.strategies.swing.constants import (
    SWING_CORE_RULE_POINTS,
    SWING_RS_POINTS,
    SWING_RULE_COUNT,
    SWING_VOLUME_POINTS,
)
from quant_hub.strategies.swing.scoring import (
    SWING_MAX_PENALTY,
    SWING_PENALTY_RUBRIC,
    SWING_RULE_POINTS,
    SWING_SCORE_RUBRIC,
)

SWING_GUIDE_TITLE = "Swing Setup Quality Rubric"
SWING_GUIDE_INTRO = (
    "Setup **quality score (0–100)** = **base** (partial credit on 5 setup rules + RS + volume) "
    f"**− penalties**. Core rules earn up to {SWING_CORE_RULE_POINTS} pts each (80 total); "
    f"RS vs SPY up to {SWING_RS_POINTS}; pullback volume up to {SWING_VOLUME_POINTS}. "
    f"Penalties capped at −{SWING_MAX_PENALTY:.0f}. "
    "**Setup gate** still requires all 5 hard checks (ATR pullback band included)."
)


def render_swing_score_guide(*, in_sidebar: bool = False) -> None:
    target = st.sidebar if in_sidebar else st
    target.markdown(f"##### {SWING_GUIDE_TITLE}")
    target.markdown(SWING_GUIDE_INTRO)

    target.markdown("**Base components (partial credit)**")
    rubric_caps = (
        *([SWING_CORE_RULE_POINTS] * 5),
        SWING_RS_POINTS,
        SWING_VOLUME_POINTS,
    )
    for index, ((name, detail), cap) in enumerate(zip(SWING_SCORE_RUBRIC, rubric_caps, strict=True), start=1):
        target.markdown(f"{index}. **{name}** — {detail} (0–{cap} pts)")

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
        f"Confirmed setups can score below 100 if chase, RSI stretch, RS laggard, or heavy volume apply. "
        f"Near-misses use the same {SWING_RULE_COUNT} core rules plus RS/volume (max 100 base) minus penalties."
    )
