"""Interactive Full Universe detail panel and table helpers."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_hub.config import LAUNCHPAD_TIER1_NORMALIZED_MIN, LAUNCHPAD_TIER2_NORMALIZED_MIN
from quant_hub.dashboard.viz.components import (
    apply_chart_style,
    render_ticker_news_panel,
    tier_badge_html,
)
from quant_hub.dashboard.viz.data import LAUNCHPAD_SCORE_LABELS, scores_to_dataframe
from quant_hub.dashboard.viz.design_tokens import COLORS
from quant_hub.dashboard.viz.navigation import set_detail_ticker, ticker_link_html
from quant_hub.dashboard.viz.styles import PLOTLY_CONFIG
from quant_hub.dashboard.viz.table_helpers import merge_column_config
from quant_hub.filters.eligibility import FILTER_LABELS

SORT_OPTIONS = {
    "Final Score": "final_score",
    "RS vs Market": "RS vs Market",
    "Compression": "Compression",
    "Technical Score": "tech_score",
}


def render_universe_summary(full_df: pd.DataFrame) -> None:
    tiers = full_df["tier"].value_counts()
    eligible = int(full_df["eligible"].sum())
    cols = st.columns(5)
    cols[0].metric("Universe", len(full_df))
    cols[1].metric("Eligible", eligible)
    cols[2].metric("Tier 1", int(tiers.get("Tier 1", 0)))
    cols[3].metric("Tier 2", int(tiers.get("Tier 2", 0)))
    avg = full_df.loc[full_df["eligible"], "final_score"].mean()
    cols[4].metric("Avg Score (eligible)", f"{avg:.1f}" if eligible else "—")


def apply_universe_controls(full_df: pd.DataFrame) -> pd.DataFrame:
    st.markdown("##### Explore the universe")
    c1, c2 = st.columns([2, 1])
    sort_label = c1.selectbox("Sort by", list(SORT_OPTIONS.keys()), key="universe_sort")
    sort_col = SORT_OPTIONS[sort_label]
    ascending = c2.toggle("Ascending", value=False, key="universe_sort_asc")

    result = full_df.copy()
    if sort_col in result.columns:
        result = result.sort_values(sort_col, ascending=ascending, na_position="last")
    return result


def _mini_score_chart(ticker_data: dict, ticker: str) -> go.Figure | None:
    score_df = scores_to_dataframe(ticker_data)
    if score_df.empty:
        return None
    top = score_df.nlargest(6, "score")
    scores = ticker_data.get("scores") or {}
    custom = [
        f"<b>{row['component']}</b><br>{scores.get(row['key'], {}).get('meaning', '')}"
        for _, row in top.iterrows()
    ]

    fig = go.Figure(
        go.Bar(
            x=top["score"],
            y=top["component"],
            orientation="h",
            marker_color=COLORS["primary"],
            text=[f"{s:.0f}/{m:.0f}" for s, m in zip(top["score"], top["max"], strict=True)],
            textposition="outside",
            customdata=custom,
            hovertemplate="%{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"{ticker} — top factors",
        height=300,
        margin=dict(l=8, r=8, t=44, b=8),
        xaxis_title="Points",
    )
    return apply_chart_style(fig)


def render_universe_detail_panel(ticker: str, ticker_data: dict) -> None:
    summary = ticker_data.get("summary") or {}
    st.markdown(
        f"### {ticker_link_html(ticker)} {tier_badge_html(ticker_data.get('tier', 'filtered'))}",
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    cols[0].metric(
        "Final Score",
        f"{summary.get('final_adjusted_score', 0):.1f}",
        help="Regime-adjusted composite. High conviction usually needs ≥70 with strong components.",
    )
    cols[1].metric(
        "Universe Rank",
        f"{summary.get('normalized_score', 0):.1f}",
        help="Percentile vs this scan universe. Watchlist cutoff is 65; high conviction starts at 80.",
    )
    cols[2].metric("Sector ETF", ticker_data.get("sector_etf") or "—")
    cols[3].metric("Eligible", "Yes" if ticker_data.get("eligible") else "No")

    fail_reason = ticker_data.get("eligibility", {}).get("fail_reason")
    if ticker_data.get("eligible") and ticker_data.get("tier_reason"):
        st.success(ticker_data["tier_reason"])
    elif fail_reason:
        st.warning(FILTER_LABELS.get(fail_reason, fail_reason))

    fig = _mini_score_chart(ticker_data, ticker)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    if st.button("Open full profile", key=f"open_profile_{ticker}", use_container_width=True):
        set_detail_ticker(ticker)
        st.rerun()

    with st.expander("Live market snapshot", expanded=False):
        render_ticker_news_panel(ticker, compact=True)


# Launchpad factor columns (label -> max points) surfaced individually in the table.
LAUNCHPAD_FACTOR_MAX = {
    "MACD Zero-Line": 25,
    "Squeeze Intensity": 40,
    "Candle Tightness": 15,
    "Volume Vacuum": 30,
    "Trend & Proximity": 15,
}


def universe_table_column_config() -> dict:
    config = {
        "eligible": st.column_config.CheckboxColumn(
            "Eligible",
            help="Passed all trend, liquidity, and price-stability filters.",
        ),
        "final_score": st.column_config.ProgressColumn(
            "Final Score",
            format="%.1f",
            min_value=0,
            max_value=100,
            help="Regime-adjusted score. Compare within the same scan date and universe.",
        ),
        "normalized_score": st.column_config.NumberColumn(
            "Universe Rank",
            format="%.1f",
            help=(
                f"0–100 rank vs this universe. ≥{LAUNCHPAD_TIER2_NORMALIZED_MIN:.0f} watchlist, "
                f"≥{LAUNCHPAD_TIER1_NORMALIZED_MIN:.0f} high-conviction candidate."
            ),
        ),
        "top_factors": st.column_config.TextColumn(
            "Top Factors",
            width="large",
            help="Top 3 Launchpad factors ranked by percentage of available points.",
        ),
        "tier_reason": st.column_config.TextColumn(
            "Tier Note",
            width="large",
            help="Why this tier was assigned — hover row and open profile for full signal readout.",
        ),
        "filter_label": st.column_config.TextColumn("Exclusion", width="medium"),
    }

    config["tech_score"] = st.column_config.NumberColumn(
        "Raw Total",
        format="%.0f",
        help="Sum of the five Launchpad factors (max 100) = the final score.",
    )
    for label, max_pts in LAUNCHPAD_FACTOR_MAX.items():
        config[label] = st.column_config.NumberColumn(
            label,
            format="%.0f",
            help=f"{label} factor score (0–{max_pts}).",
        )

    return merge_column_config(config)


def universe_display_columns(
    table_df: pd.DataFrame,
) -> list[str]:
    preferred = [
        "ticker",
        "tier",
        "eligible",
        "final_score",
        *LAUNCHPAD_SCORE_LABELS.values(),
        "tech_score",
        "sector_etf",
        "top_factors",
        "tier_reason",
        "filter_label",
    ]
    return [column for column in preferred if column in table_df.columns]
