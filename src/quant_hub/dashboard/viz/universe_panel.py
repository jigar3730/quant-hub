"""Interactive Full Universe detail panel and table helpers."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_hub.filters.eligibility import FILTER_LABELS
from quant_hub.dashboard.viz.components import (
    apply_chart_style,
    render_ticker_news_panel,
    tier_badge_html,
)
from quant_hub.dashboard.viz.data import scores_to_dataframe
from quant_hub.dashboard.viz.navigation import set_detail_ticker, ticker_link_html

SORT_OPTIONS = {
    "Final Score": "final_score",
    "RS vs Market": "RS vs Market",
    "Compression": "Compression",
    "Revenue YoY %": "revenue_yoy_pct",
    "EPS Growth %": "eps_growth_pct",
    "Technical Score": "tech_score",
    "Fundamental Score": "fund_score",
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
    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    sort_label = c1.selectbox("Sort by", list(SORT_OPTIONS.keys()), key="universe_sort")
    sort_col = SORT_OPTIONS[sort_label]
    ascending = c2.toggle("Ascending", value=False, key="universe_sort_asc")

    sectors = sorted(full_df["sector_etf"].dropna().unique().tolist())
    sector_pick = c3.multiselect("Sector ETF", sectors, key="universe_sector_filter")

    view_mode = c4.selectbox("View", ["All", "Eligible", "Actionable"], key="universe_view")

    result = full_df.copy()
    if sector_pick:
        result = result[result["sector_etf"].isin(sector_pick)]
    if view_mode == "Eligible":
        result = result[result["eligible"]]
    elif view_mode == "Actionable":
        result = result[result["tier"].isin(["Tier 1", "Tier 2"])]

    if sort_col in result.columns:
        result = result.sort_values(sort_col, ascending=ascending, na_position="last")
    return result


def _mini_score_chart(ticker_data: dict, ticker: str) -> go.Figure | None:
    score_df = scores_to_dataframe(ticker_data)
    if score_df.empty:
        return None
    top = score_df.nlargest(6, "score")
    fig = go.Figure(
        go.Bar(
            x=top["score"],
            y=top["component"],
            orientation="h",
            marker_color="#3b82f6",
            text=[f"{s:.0f}/{m:.0f}" for s, m in zip(top["score"], top["max"], strict=True)],
            textposition="outside",
        )
    )
    fig.update_layout(
        title=f"{ticker} — top signals",
        height=260,
        margin=dict(l=8, r=8, t=40, b=8),
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
    cols[0].metric("Final Score", f"{summary.get('final_adjusted_score', 0):.1f}")
    cols[1].metric("Normalized", f"{summary.get('normalized_score', 0):.1f}")
    cols[2].metric("Sector ETF", ticker_data.get("sector_etf") or "—")
    cols[3].metric("Eligible", "Yes" if ticker_data.get("eligible") else "No")

    fail_reason = ticker_data.get("eligibility", {}).get("fail_reason")
    if ticker_data.get("eligible") and ticker_data.get("tier_reason"):
        st.success(ticker_data["tier_reason"])
    elif fail_reason:
        st.warning(FILTER_LABELS.get(fail_reason, fail_reason))

    fig = _mini_score_chart(ticker_data, ticker)
    if fig:
        st.plotly_chart(fig, use_container_width=True)

    if st.button("Open full profile", key=f"open_profile_{ticker}", use_container_width=True):
        set_detail_ticker(ticker)
        st.rerun()

    with st.expander("Live market snapshot", expanded=False):
        render_ticker_news_panel(ticker, compact=True)


def universe_table_column_config() -> dict:
    return {
        "eligible": st.column_config.CheckboxColumn("Eligible"),
        "final_score": st.column_config.ProgressColumn(
            "Final Score",
            format="%.1f",
            min_value=0,
            max_value=100,
        ),
        "normalized_score": st.column_config.NumberColumn("Normalized", format="%.1f"),
        "tech_score": st.column_config.NumberColumn("Technical", format="%.0f"),
        "fund_score": st.column_config.NumberColumn("Fundamental", format="%.0f"),
        "revenue_yoy_pct": st.column_config.NumberColumn("Rev YoY %", format="%.1f"),
        "eps_growth_pct": st.column_config.NumberColumn("EPS Gr %", format="%.1f"),
        "RS vs Market": st.column_config.NumberColumn("RS Mkt", format="%.0f"),
        "Compression": st.column_config.NumberColumn("Compress", format="%.0f"),
        "top_signal": st.column_config.TextColumn("Top Signal", width="medium"),
        "tier_reason": st.column_config.TextColumn("Tier Note", width="large"),
        "filter_label": st.column_config.TextColumn("Exclusion", width="medium"),
    }


def universe_display_columns(table_df: pd.DataFrame) -> list[str]:
    preferred = [
        "ticker",
        "tier",
        "eligible",
        "final_score",
        "normalized_score",
        "top_signal",
        "tech_score",
        "fund_score",
        "sector_etf",
        "RS vs Market",
        "Compression",
        "Accumulation",
        "Revenue",
        "EPS",
        "revenue_yoy_pct",
        "eps_growth_pct",
        "tier_reason",
        "filter_label",
    ]
    return [column for column in preferred if column in table_df.columns]
