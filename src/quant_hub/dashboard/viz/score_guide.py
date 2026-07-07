"""Human-readable score component cheat sheet for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class ScoreMetricGuide:
    key: str
    name: str
    description: str
    look_for: str


@dataclass(frozen=True)
class ScoreGuideSection:
    title: str
    metrics: tuple[ScoreMetricGuide, ...]


SCORE_GUIDE_TITLE = "Stock Metrics Cheat Sheet: How to Find Winning Stocks"

SCORE_GUIDE_INTRO = (
    "Think of these metrics as a **scouting report** for a stock. Instead of guessing, "
    "these numbers tell you how much muscle a stock has compared to its competition."
)

SCORE_GUIDE_PERCENTILE_NOTE = (
    "💡 **Important note:** Percentiles and ranks are like grading on a curve. A stock's "
    "score depends entirely on the **classroom (universe)** it's in. A stock might look "
    "like an A+ student among tech stocks, but only a B among all stocks in the market."
)

SCORE_GUIDE_SECTIONS: tuple[ScoreGuideSection, ...] = (
    ScoreGuideSection(
        title="1. Market Momentum (The Trend Followers)",
        metrics=(
            ScoreMetricGuide(
                key="rs_market",
                name="RS Market (Relative Strength vs. Market)",
                description=(
                    "Measures if the stock is beating the S&P 500 over the last 3 to 6 months."
                ),
                look_for=(
                    "Higher scores. You want to buy stocks that are moving up faster "
                    "than the general market."
                ),
            ),
            ScoreMetricGuide(
                key="rs_sector",
                name="RS Sector (Relative Strength vs. Industry)",
                description=(
                    "Measures if the stock is beating its direct competitors "
                    "(e.g., Apple vs. other tech stocks)."
                ),
                look_for=(
                    "Top ranks. Winning stocks usually lead their specific industry forward."
                ),
            ),
        ),
    ),
    ScoreGuideSection(
        title="2. The Money Trail (Volume & Buyers)",
        metrics=(
            ScoreMetricGuide(
                key="accumulation",
                name="Accumulation",
                description=(
                    'Compares the volume of shares bought on "up days" versus sold on '
                    '"down days" over the last month.'
                ),
                look_for=(
                    "Above 1.0. Anything above 1 means big institutional investors "
                    "(like mutual funds) are quietly buying up shares."
                ),
            ),
            ScoreMetricGuide(
                key="relative_volume",
                name="Relative Volume (RVOL)",
                description=(
                    "Compares today's trading volume against its 20-day average."
                ),
                look_for=(
                    "A sudden surge. High volume means institutions are actively piling in, "
                    "which often starts a major price run."
                ),
            ),
        ),
    ),
    ScoreGuideSection(
        title="3. Chart Layout & Timing (The Setup)",
        metrics=(
            ScoreMetricGuide(
                key="compression",
                name="Compression (The Volatility Squeeze)",
                description="Measures how tight the stock's price moves have become.",
                look_for=(
                    "Low percentile numbers. Think of this like a coiled spring. When the "
                    "price gets tight, a massive breakout up or down is usually right around "
                    "the corner."
                ),
            ),
            ScoreMetricGuide(
                key="pattern",
                name="Pattern (The Base Quality)",
                description=(
                    "A 5-point checklist verifying if the stock is safely resting near "
                    "its 52-week highs."
                ),
                look_for=(
                    "High checklist scores. This ensures you aren't buying a stock that is "
                    "crashing, but rather one building a launchpad."
                ),
            ),
            ScoreMetricGuide(
                key="resistance",
                name="Resistance",
                description=(
                    "How close the current price is to its recent peaks (50 to 65 days ago)."
                ),
                look_for=(
                    "Very close (small distance). The closer it is to breaking past old "
                    "resistance, the sooner it can skyrocket into new high territory."
                ),
            ),
        ),
    ),
)


def _all_metrics() -> tuple[ScoreMetricGuide, ...]:
    return tuple(m for section in SCORE_GUIDE_SECTIONS for m in section.metrics)


# Short captions on ticker detail score cards.
COMPONENT_HELP: dict[str, str] = {m.key: m.look_for for m in _all_metrics()}

# One-line summaries for compact UI.
COMPONENT_SUMMARY: dict[str, str] = {m.key: m.description for m in _all_metrics()}


def render_score_component_guide(*, in_sidebar: bool = True) -> None:
    """Render the full analyst-friendly cheat sheet."""
    target = st.sidebar if in_sidebar else st
    target.markdown(f"##### {SCORE_GUIDE_TITLE}")
    target.markdown(SCORE_GUIDE_INTRO)
    target.markdown(SCORE_GUIDE_PERCENTILE_NOTE)
    target.divider()
    for section in SCORE_GUIDE_SECTIONS:
        target.markdown(f"**{section.title}**")
        for metric in section.metrics:
            target.markdown(f"**{metric.name}**")
            target.caption(metric.description)
            target.markdown(f"**What to look for:** {metric.look_for}")
        target.markdown("")
