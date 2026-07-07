"""Launchpad Reversal dashboard tab renderers."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from quant_hub.dashboard.viz.components import (
    apply_chart_style,
    get_ticker_by_name,
    render_compare_radar,
    render_exclusion_chart,
    render_heatmap,
    render_regime_panel,
    render_scan_header,
    render_score_histogram,
    render_ticker_detail,
    render_tier_chart,
    tier_badge_html,
)
from quant_hub.dashboard.viz.data import (
    LAUNCHPAD_SCORE_LABELS,
    full_universe_dataframe,
    score_heatmap_dataframe,
    TIER_COLORS,
)
from quant_hub.dashboard.viz.labels import tier_friendly
from quant_hub.dashboard.viz.launchpad_filters import (
    LaunchpadFilters,
    apply_launchpad_filters,
    launchpad_scatter_dataframe,
)
from quant_hub.dashboard.viz.navigation import (
    dashboard_ticker_link_html,
    set_detail_ticker,
    ticker_link_html,
)
from quant_hub.dashboard.viz.styles import PLOTLY_CONFIG
from quant_hub.dashboard.viz.table_helpers import (
    merge_column_config,
    table_column_order,
    with_yahoo_ticker_links,
)
from quant_hub.dashboard.viz.ticker_history_components import render_ticker_history_panel
from quant_hub.dashboard.viz.universe_panel import (
    apply_universe_controls,
    render_universe_detail_panel,
    render_universe_summary,
    universe_display_columns,
    universe_table_column_config,
)
from quant_hub.dashboard.viz.ux_helpers import render_near_miss_panel
from quant_hub.infrastructure.postgres.repository import ScanRepository


def _render_launchpad_scatter(scatter_df: pd.DataFrame):
    fig = px.scatter(
        scatter_df,
        x="macd_zero_line",
        y="ma_tightness",
        text="ticker",
        size="final_score",
        color="tier",
        color_discrete_map=TIER_COLORS,
        hover_data=["final_score", "tier"],
        labels={
            "macd_zero_line": "MACD Zero-Line Score",
            "ma_tightness": "MA Tightness Score",
            "final_score": "Final Score",
        },
    )
    fig.update_traces(textposition="top center", marker=dict(line=dict(width=1, color="white")))
    fig.update_layout(title="MACD Ignition vs MA Tightness")
    return apply_chart_style(fig, height=400)


def render_overview_tab(
    *,
    report_path: str,
    summary: dict,
    regime: dict,
    df: pd.DataFrame,
    tickers: list[dict],
    filters: LaunchpadFilters,
) -> None:
    render_regime_panel(regime)

    col_left, col_right = st.columns(2)
    with col_left:
        st.plotly_chart(
            render_tier_chart(summary["tier_counts"]),
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )
    with col_right:
        exclusion_fig = render_exclusion_chart(summary.get("filter_breakdown", {}))
        if exclusion_fig:
            st.plotly_chart(exclusion_fig, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.success("All tickers in universe were evaluated for scoring.")

    filtered_df = apply_launchpad_filters(df, filters)
    eligible_df = filtered_df[filtered_df["eligible"]]
    if eligible_df.empty:
        return

    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(
            render_score_histogram(eligible_df),
            use_container_width=True,
            config=PLOTLY_CONFIG,
        )
    with col_b:
        eligible_tickers = {row["ticker"] for _, row in eligible_df.iterrows()}
        heat_df = score_heatmap_dataframe(
            [t for t in tickers if t["ticker"] in eligible_tickers],
            eligible_only=False,
            strategy_id="launchpad",
        )
        if len(heat_df) > 1:
            st.plotly_chart(render_heatmap(heat_df), use_container_width=True, config=PLOTLY_CONFIG)

    scatter_df = launchpad_scatter_dataframe(
        [t for t in tickers if t["ticker"] in set(eligible_df["ticker"])]
    )
    if scatter_df.empty:
        return
    st.plotly_chart(_render_launchpad_scatter(scatter_df), use_container_width=True, config=PLOTLY_CONFIG)
    links = " · ".join(ticker_link_html(symbol) for symbol in scatter_df["ticker"].head(20))
    st.markdown(links, unsafe_allow_html=True)


def render_all_tickers_tab(
    *,
    tickers: list[dict],
    filters: LaunchpadFilters,
    detail_ticker: str | None,
) -> str | None:
    st.markdown("### Full Universe")
    full_df = apply_launchpad_filters(full_universe_dataframe(tickers, strategy_id="launchpad"), filters)
    if full_df.empty:
        st.warning("No tickers match the current filters.")
        return detail_ticker

    render_universe_summary(full_df)
    table_df = apply_universe_controls(full_df)
    if table_df.empty:
        st.warning("No tickers match the selected view.")
        return detail_ticker

    display_cols = universe_display_columns(table_df, strategy_id="launchpad")
    shown_df = with_yahoo_ticker_links(table_df[display_cols].copy())

    table_col, detail_col = st.columns([1.55, 1], gap="large")
    with table_col:
        selection = st.dataframe(
            shown_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="launchpad_all_tickers_select",
            column_config=universe_table_column_config(strategy_id="launchpad"),
            column_order=table_column_order(display_cols),
        )
        st.download_button(
            "Download filtered CSV",
            table_df.to_csv(index=False).encode(),
            file_name="launchpad_scan_full.csv",
            mime="text/csv",
        )

    active_ticker = detail_ticker
    if selection.selection.rows:
        active_ticker = shown_df.iloc[selection.selection.rows[0]]["ticker"]
        set_detail_ticker(active_ticker)
    elif not active_ticker and not shown_df.empty:
        active_ticker = shown_df.iloc[0]["ticker"]

    with detail_col:
        if active_ticker:
            ticker_data = get_ticker_by_name(tickers, active_ticker)
            if ticker_data:
                render_universe_detail_panel(active_ticker, ticker_data)
            else:
                st.info("Select a row to preview ticker details.")
        else:
            st.info("Select a row to preview ticker details.")

    return active_ticker


def render_ticker_detail_tab(
    *,
    tickers: list[dict],
    all_symbols: list[str],
    detail_ticker: str | None,
    scan_date: str | None = None,
    repo: ScanRepository | None = None,
) -> None:
    st.markdown("### Ticker Profile")
    active = detail_ticker
    if all_symbols:
        pick_index = all_symbols.index(detail_ticker) if detail_ticker in all_symbols else 0
        active = st.selectbox(
            "Select ticker",
            all_symbols,
            index=pick_index,
            key="launchpad_detail_tab_pick",
        )
        if active != detail_ticker:
            set_detail_ticker(active)
    elif detail_ticker:
        active = detail_ticker
    else:
        st.info("Select a ticker from the sidebar lookup or universe table.")
        return

    ticker_data = get_ticker_by_name(tickers, active) if active else None
    if ticker_data:
        render_ticker_detail(
            active,
            ticker_data,
            scan_date=scan_date,
            repo=repo,
            strategy_id="launchpad",
        )
    elif active and repo is not None:
        render_ticker_history_panel(repo, active, key_prefix="launchpad_orphan")
    elif active:
        st.warning(f"No data for {active} in this scan.")


def render_watchlist_tab(*, df: pd.DataFrame, tickers: list[dict], filters: LaunchpadFilters) -> None:
    st.markdown("### Actionable Launchpad candidates")
    actionable = apply_launchpad_filters(df, filters)
    actionable = actionable[actionable["tier"].isin(["Tier 1", "Tier 2"])].sort_values(
        "final_score",
        ascending=False,
    )
    if actionable.empty:
        st.warning("No Tier 1 or Tier 2 names in this scan.")
        render_near_miss_panel(df)
        return

    st.download_button(
        "Download watchlist CSV",
        actionable.to_csv(index=False).encode(),
        file_name="launchpad_watchlist.csv",
        mime="text/csv",
    )

    for _, row in actionable.iterrows():
        symbol = row["ticker"]
        ticker_data = get_ticker_by_name(tickers, symbol)
        if not ticker_data:
            continue
        tier_label = tier_friendly(row["tier"])
        with st.expander(
            f"{symbol} — {tier_label} — Score {row['final_score']:.1f}",
            expanded=row["tier"] == "Tier 1",
        ):
            st.markdown(
                f"Yahoo Finance: {ticker_link_html(symbol)} {tier_badge_html(row['tier'])}",
                unsafe_allow_html=True,
            )
            st.caption(ticker_data.get("tier_reason", ""))


def render_compare_tab(*, df: pd.DataFrame, tickers: list[dict], filters: LaunchpadFilters) -> None:
    st.markdown("### Compare Tickers")
    filtered = apply_launchpad_filters(df, filters)
    eligible_names = (
        filtered[filtered["eligible"]]
        .sort_values("final_score", ascending=False)["ticker"]
        .tolist()
    )
    if len(eligible_names) < 2:
        st.warning("Need at least 2 eligible tickers to compare.")
        return

    picked = st.multiselect(
        "Select 2–3 tickers",
        eligible_names,
        default=eligible_names[: min(3, len(eligible_names))],
        max_selections=3,
    )
    if len(picked) < 2:
        st.info("Select at least 2 tickers to compare.")
        return

    compare_data = [get_ticker_by_name(tickers, name) for name in picked]
    compare_data = [item for item in compare_data if item]
    fig = render_compare_radar(compare_data)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    compare_rows = []
    for ticker_data in compare_data:
        summary = ticker_data.get("summary", {})
        row = {
            "ticker": ticker_data["ticker"],
            "tier": tier_friendly(ticker_data["tier"], short=True),
            "final_score": summary.get("final_adjusted_score", 0),
            "sector_etf": ticker_data.get("sector_etf"),
        }
        scores = ticker_data.get("scores") or {}
        for key, label in LAUNCHPAD_SCORE_LABELS.items():
            row[label] = scores.get(key, {}).get("score", 0)
        compare_rows.append(row)

    compare_df = with_yahoo_ticker_links(pd.DataFrame(compare_rows))
    base_cols = [column for column in compare_df.columns if column != "ticker_link"]
    st.dataframe(
        compare_df,
        use_container_width=True,
        hide_index=True,
        column_config=merge_column_config({
            "final_score": st.column_config.NumberColumn("Final Score", format="%.1f"),
        }),
        column_order=table_column_order(base_cols),
    )


def render_launchpad_header(
    *,
    report_path: str,
    summary: dict,
    regime: dict,
    detail_ticker: str | None,
    scan_date: str | None = None,
) -> None:
    render_scan_header(
        report_path,
        summary,
        regime,
        scan_date=scan_date,
        title="Launchpad Reversal",
    )
    if not detail_ticker:
        return
    link = dashboard_ticker_link_html(detail_ticker)
    st.markdown(
        f'<div class="info-card">Viewing profile: <strong>{link}</strong> '
        f"— open the <em>Ticker Detail</em> tab for the full scan breakdown.</div>",
        unsafe_allow_html=True,
    )
