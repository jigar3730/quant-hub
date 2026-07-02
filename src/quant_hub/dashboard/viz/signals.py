"""Actionable signal summaries and tooltips for scan results."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from quant_hub.dashboard.viz.data import SCORE_LABELS
from quant_hub.dashboard.viz.score_guide import COMPONENT_SUMMARY, _all_metrics

METRIC_BY_KEY = {m.key: m for m in _all_metrics()}

# Minimum normalized score for watchlist (Tier 2) in breakout strategy.
WATCHLIST_NORM = 65.0
HIGH_CONVICTION_NORM = 80.0


@dataclass(frozen=True)
class ComponentSignal:
    key: str
    label: str
    score: float
    max_pts: float
    pct: float
    meaning: str
    action: str


def score_pct(comp: dict) -> float:
    max_pts = float(comp.get("max") or 0)
    if max_pts <= 0:
        return 0.0
    return float(comp.get("score", 0)) / max_pts * 100.0


def _band(pct: float) -> str:
    if pct >= 85:
        return "strong"
    if pct >= 60:
        return "ok"
    if pct >= 35:
        return "weak"
    return "gap"


def component_action(key: str, comp: dict) -> str:
    """One actionable sentence for a component score."""
    pct = score_pct(comp)
    band = _band(pct)
    meaning = (comp.get("meaning") or "").strip()
    score = float(comp.get("score", 0))
    max_pts = float(comp.get("max", 0))

    if key == "compression":
        if band == "gap":
            return (
                f"Wide range ({score:.0f}/{max_pts:.0f}) — not in a squeeze yet. "
                "Wait for volatility to tighten before expecting a breakout."
            )
        if band == "weak":
            return (
                f"Mild squeeze ({score:.0f}/{max_pts:.0f}). "
                "Some coiling — watch for further range contraction."
            )
        return (
            f"Tight squeeze ({score:.0f}/{max_pts:.0f}). "
            "Spring is coiled — a sharp move may be near if volume confirms."
        )

    if key == "rs_market":
        if band == "strong":
            return (
                f"Outperforming SPY ({score:.0f}/{max_pts:.0f}). "
                "Price trend supports the long side vs the broad market."
            )
        if band == "ok":
            return (
                f"Keeping pace with the market ({score:.0f}/{max_pts:.0f}). "
                "Not a leader — needs stronger relative momentum to upgrade."
            )
        return (
            f"Lagging SPY ({score:.0f}/{max_pts:.0f}). "
            "Avoid chasing until relative strength improves."
        )

    if key == "rs_sector":
        if band in ("strong", "ok"):
            return (
                f"Competitive within its sector ({score:.0f}/{max_pts:.0f}). "
                f"{meaning or 'Compare peers in the same industry group.'}"
            )
        return (
            f"Trailing sector peers ({score:.0f}/{max_pts:.0f}). "
            "Industry tailwind is missing — lower priority vs sector leaders."
        )

    if key == "accumulation":
        if band == "strong":
            return (
                f"Heavy up-day volume ({score:.0f}/{max_pts:.0f}). "
                "Institutions appear to be accumulating — bullish flow."
            )
        if band == "ok":
            return (
                f"Balanced-to-positive volume ({score:.0f}/{max_pts:.0f}). "
                "Some buying interest — confirm with a volume surge on breakouts."
            )
        return (
            f"Weak accumulation ({score:.0f}/{max_pts:.0f}). "
            "Distribution may be underway — wait for buyers to step in."
        )

    if key == "relative_volume":
        if band == "strong":
            return (
                f"Volume surge ({score:.0f}/{max_pts:.0f}). "
                "Today's activity signals institutional participation."
            )
        if band == "ok":
            return (
                f"Above-average volume ({score:.0f}/{max_pts:.0f}). "
                "Interest is picking up — watch for follow-through."
            )
        return (
            f"Quiet volume ({score:.0f}/{max_pts:.0f}). "
            "Breakouts need volume — low RVOL reduces conviction."
        )

    if key == "pattern":
        if band == "strong":
            return (
                f"Solid base ({score:.0f}/{max_pts:.0f}). "
                "Chart structure near highs supports a continuation setup."
            )
        return (
            f"Imperfect base ({score:.0f}/{max_pts:.0f}). "
            "Pattern quality is mixed — require stronger price action before acting."
        )

    if key == "resistance":
        if band == "strong":
            return (
                f"At/near resistance ({score:.0f}/{max_pts:.0f}). "
                "A clean break above recent highs could trigger momentum."
            )
        return (
            f"Far from resistance ({score:.0f}/{max_pts:.0f}). "
            "More room to run to the pivot — less immediate breakout timing."
        )

    if key == "revenue":
        if band == "strong":
            return (
                f"Strong sales growth ({score:.0f}/{max_pts:.0f}). "
                f"{meaning or 'Top-line is expanding — fundamental tailwind.'}"
            )
        if band == "ok":
            return (
                f"Moderate revenue growth ({score:.0f}/{max_pts:.0f}). "
                "Fundamentals are acceptable but not a primary driver."
            )
        return (
            f"Soft revenue trend ({score:.0f}/{max_pts:.0f}). "
            "Sales growth is a headwind — lean on technicals only with caution."
        )

    if key == "eps":
        if band == "strong":
            return (
                f"Strong profit growth ({score:.0f}/{max_pts:.0f}). "
                f"{meaning or 'Earnings momentum supports the story.'}"
            )
        if band == "ok":
            return (
                f"Steady EPS trend ({score:.0f}/{max_pts:.0f}). "
                "Profits are fine — not accelerating enough to lead the scan."
            )
        return (
            f"Weak EPS ({score:.0f}/{max_pts:.0f}). "
            "Earnings growth is insufficient — downgrade fundamental conviction."
        )

    summary = COMPONENT_SUMMARY.get(key, meaning)
    if band == "strong":
        return f"Strength: {summary} ({score:.0f}/{max_pts:.0f} pts)."
    if band == "gap":
        return f"Gap to fix: {summary} ({score:.0f}/{max_pts:.0f} pts)."
    return f"{summary} ({score:.0f}/{max_pts:.0f} pts)."


def rank_components(scores: dict, *, n: int = 3) -> list[ComponentSignal]:
    """Top components by % of max points (fair across different weights)."""
    ranked: list[ComponentSignal] = []
    for key, comp in scores.items():
        if not comp or key not in SCORE_LABELS:
            continue
        max_pts = float(comp.get("max") or 0)
        if max_pts <= 0:
            continue
        score = float(comp.get("score", 0))
        pct = score / max_pts * 100.0
        ranked.append(
            ComponentSignal(
                key=key,
                label=SCORE_LABELS[key],
                score=score,
                max_pts=max_pts,
                pct=pct,
                meaning=(comp.get("meaning") or ""),
                action=component_action(key, comp),
            )
        )
    ranked.sort(key=lambda s: (s.pct, s.score), reverse=True)
    return ranked[:n]


def weakest_components(scores: dict, *, n: int = 2) -> list[ComponentSignal]:
    """Lowest % scores — usually explain why a name is not actionable."""
    all_ranked = rank_components(scores, n=len(scores))
    all_ranked.sort(key=lambda s: (s.pct, s.score))
    return [s for s in all_ranked if s.pct < 60][:n]


def top_signals_short(scores: dict, *, n: int = 3) -> str:
    """Compact table column: label score/max (band)."""
    parts = []
    for sig in rank_components(scores, n=n):
        band = _band(sig.pct)
        tag = {"strong": "✓", "ok": "~", "weak": "!", "gap": "✗"}.get(band, "")
        parts.append(f"{sig.label} {sig.score:.0f}/{sig.max_pts:.0f}{tag}")
    return " · ".join(parts)


def top_signals_tooltip(scores: dict, *, n: int = 3) -> str:
    """Multi-line tooltip for tables and metrics."""
    lines = []
    for sig in rank_components(scores, n=n):
        lines.append(f"• {sig.label} ({sig.score:.0f}/{sig.max_pts:.0f}, {sig.pct:.0f}%): {sig.action}")
    return "\n".join(lines)


def holding_back_summary(ticker_data: dict) -> str:
    """Why this name is not Tier 1/2 — actionable gaps."""
    scores = ticker_data.get("scores") or {}
    summary = ticker_data.get("summary") or {}
    norm = float(summary.get("normalized_score") or 0)
    tier = ticker_data.get("tier", "")
    lines: list[str] = []

    if tier in ("Tier 1", "Tier 2"):
        return "Meets actionable tier thresholds — review entry timing and risk."

    if norm < WATCHLIST_NORM:
        gap = WATCHLIST_NORM - norm
        lines.append(
            f"Universe rank {norm:.1f} is {gap:.1f} pts below the watchlist cutoff (65). "
            "Needs stronger overall score vs this universe."
        )
    elif norm < HIGH_CONVICTION_NORM and tier != "Tier 1":
        lines.append(
            f"Universe rank {norm:.1f} is in watchlist range but missing high-conviction "
            "criteria (norm ≥80, final ≥70, compression ≥8, volume confirmation)."
        )

    for sig in weakest_components(scores, n=2):
        if sig.pct < 60:
            lines.append(sig.action)

    if not lines and ticker_data.get("tier_reason"):
        return str(ticker_data["tier_reason"])
    return " ".join(lines)


def signal_insights(ticker_data: dict) -> dict[str, str | list[str]]:
    """Strengths, gaps, and next step for analyst review."""
    scores = ticker_data.get("scores") or {}
    strengths = [s.action for s in rank_components(scores, n=3)]
    gaps = [s.action for s in weakest_components(scores, n=2)]
    return {
        "strengths": strengths,
        "gaps": gaps,
        "holding_back": holding_back_summary(ticker_data),
        "top_short": top_signals_short(scores),
        "top_tooltip": top_signals_tooltip(scores),
    }


def plotly_hover_texts(ticker_data: dict, *, n: int = 6) -> list[str]:
    """Hover strings aligned to chart bars (top n by score points for display order)."""
    scores = ticker_data.get("scores") or {}
    score_df_items = []
    for key, comp in scores.items():
        if not comp or key not in SCORE_LABELS:
            continue
        score_df_items.append((SCORE_LABELS[key], float(comp.get("score", 0)), key, comp))
    score_df_items.sort(key=lambda x: x[1], reverse=True)
    return [
        f"<b>{label}</b><br>{component_action(key, comp)}"
        for label, _, key, comp in score_df_items[:n]
    ]


def render_signal_insights_panel(ticker_data: dict) -> None:
    """Strengths / gaps / next step card under top-signals chart."""
    insights = signal_insights(ticker_data)
    st.markdown("##### Signal readout")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**What's working**")
        for line in insights["strengths"]:
            st.markdown(f"- {line}")
    with c2:
        st.markdown("**What's missing**")
        gaps = insights["gaps"]
        if gaps:
            for line in gaps:
                st.markdown(f"- {line}")
        else:
            st.markdown("- No major component gaps — tier rules may still apply.")
    st.info(f"**Next step:** {insights['holding_back']}")
