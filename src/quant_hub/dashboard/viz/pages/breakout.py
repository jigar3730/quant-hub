"""Breakout dashboard tab renderers."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from quant_hub.dashboard.viz.breakout_filters import (
    BreakoutFilters,
    apply_breakout_filters,
    scatter_dataframe,
)
from quant_hub.dashboard.viz.components import (
    get_ticker_by_name,
    render_compare_radar,
    render_exclusion_chart,
    render_heatmap,
    render_regime_panel,
    render_scan_header,
    render_scatter,
    render_score_histogram,
    render_ticker_detail,
    render_tier_chart,
    tier_badge_html,
)
from quant_hub.dashboard.viz.data import full_universe_dataframe, score_heatmap_dataframe
from quant_hub.dashboard.viz.navigation import set_detail_ticker, ticker_link_html
from quant_hub.dashboard.viz.universe_panel import (
    apply_universe_controls,
    render_universe_detail_panel,
    render_universe_summary,
    universe_display_columns,
    universe_table_column_config,
)


def render_overview_tab(
    *,
    report_path: str,
    summary: dict,
    regime: dict,
    df: pd.DataFrame,
    tickers: list[dict],
    filters: BreakoutFilters,
) -> None:
    render_regime_panel(regime)

    col_left, col_right = st.columns(2)
    with col_left:
        st.plotly_chart(render_tier_chart(summary["tier_counts"]), use_container_width=True)
    with col_right:
        exclusion_fig = render_exclusion_chart(summary.get("filter_breakdown", {}))
        if exclusion_fig:
            st.plotly_chart(exclusion_fig, use_container_width=True)
        else:
            st.success("All tickers in universe were evaluated for scoring.")

    filtered_df = apply_breakout_filters(df, filters)
    eligible_df = filtered_df[filtered_df["eligible"]]
    if eligible_df.empty:
        return

    col_a, col_b = st.columns(2)
    with col_a:
        st.plotly_chart(render_score_histogram(eligible_df), use_container_width=True)
    with col_b:
        eligible_tickers = {row["ticker"] for _, row in eligible_df.iterrows()}
        heat_df = score_heatmap_dataframe(
            [t for t in tickers if t["ticker"] in eligible_tickers],
            eligible_only=False,
        )
        if len(heat_df) > 1:
            st.plotly_chart(render_heatmap(heat_df), use_container_width=True)

    scatter_df = scatter_dataframe(
        [t for t in tickers if t["ticker"] in set(eligible_df["ticker"])]
    )
    if scatter_df.empty:
        return

    st.caption("Ticker labels are clickable — opens fundamentals, technical scores, and news.")
    st.plotly_chart(render_scatter(scatter_df), use_container_width=True)
    links = " · ".join(ticker_link_html(symbol) for symbol in scatter_df["ticker"].head(20))
    st.markdown(links, unsafe_allow_html=True)


def render_all_tickers_tab(
    *,
    tickers: list[dict],
    filters: BreakoutFilters,
    detail_ticker: str | None,
) -> str | None:
    st.markdown("### Full Universe")
    st.caption(
        "Sort and filter the scan results, click a row for an instant profile preview, "
        "or open the full ticker detail view."
    )

    full_df = apply_breakout_filters(full_universe_dataframe(tickers), filters)
    if full_df.empty:
        st.warning("No tickers match the current filters.")
        return detail_ticker

    render_universe_summary(full_df)
    table_df = apply_universe_controls(full_df)
    if table_df.empty:
        st.warning("No tickers match the selected view.")
        return detail_ticker

    display_cols = universe_display_columns(table_df)
    shown_df = table_df[display_cols].copy()

    table_col, detail_col = st.columns([1.55, 1], gap="large")
    with table_col:
        selection = st.dataframe(
            shown_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="all_tickers_select",
            column_config=universe_table_column_config(),
        )
        st.download_button(
            "Download filtered CSV",
            table_df.to_csv(index=False).encode(),
            file_name="breakout_scan_full.csv",
            mime="text/csv",
        )

    active_ticker = detail_ticker
    if selection.selection.rows:
        active_ticker = shown_df.iloc[selection.selection.rows[0]]["ticker"]
        set_detail_ticker(active_ticker)
    elif not active_ticker and not shown_df.empty:
        active_ticker = shown_df.iloc[0]["ticker"]

    with detail_col:
        st.markdown("##### Selected ticker")
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
) -> None:
    st.markdown("### Ticker Profile")
    st.caption("Fundamentals, technical scores, eligibility checks, news, and score history.")

    pick_index = all_symbols.index(detail_ticker) if detail_ticker in all_symbols else 0
    active = st.selectbox(
        "Select ticker",
        all_symbols,
        index=pick_index,
        key="detail_tab_pick",
    )
    if active != detail_ticker:
        set_detail_ticker(active)
    ticker_data = get_ticker_by_name(tickers, active)
    if ticker_data:
        render_ticker_detail(active, ticker_data)
    else:
        st.warning(f"No data for {active}.")


def render_watchlist_tab(
    *,
    df: pd.DataFrame,
    tickers: list[dict],
    filters: BreakoutFilters,
) -> None:
    st.markdown("### Tier 1 and Tier 2 — Actionable Candidates")
    actionable = apply_breakout_filters(df, filters)
    actionable = actionable[actionable["tier"].isin(["Tier 1", "Tier 2"])].sort_values(
        "final_score",
        ascending=False,
    )
    if actionable.empty:
        st.warning(
            "No actionable tickers in this scan. "
            "Try lowering thresholds or check market regime."
        )
        return

    for _, row in actionable.iterrows():
        symbol = row["ticker"]
        ticker_data = get_ticker_by_name(tickers, symbol)
        if not ticker_data:
            continue
        with st.expander(
            f"{symbol} — {row['tier']} — Score {row['final_score']:.1f}",
            expanded=row["tier"] == "Tier 1",
        ):
            st.markdown(
                f"Open full profile: {ticker_link_html(symbol)} {tier_badge_html(row['tier'])}",
                unsafe_allow_html=True,
            )
            st.caption(ticker_data.get("tier_reason", ""))
            cols = st.columns(4)
            cols[0].metric("Final Score", f"{row['final_score']:.1f}")
            cols[1].metric("Normalized", f"{row['normalized_score']:.1f}")
            cols[2].metric("Sector ETF", row.get("sector_etf") or "—")
            scores = ticker_data.get("scores") or {}
            if scores:
                top = sorted(
                    scores.items(),
                    key=lambda item: item[1].get("score", 0),
                    reverse=True,
                )[:3]
                top_str = ", ".join(
                    f"{key.replace('_', ' ').title()}: {value.get('score', 0):.0f}"
                    for key, value in top
                )
                top_display = top_str[:30] + "..." if len(top_str) > 30 else top_str
                cols[3].metric("Top signals", top_display)
            st.caption("Click the ticker link above for fundamentals, technicals, and news.")


def render_compare_tab(*, df: pd.DataFrame, tickers: list[dict], filters: BreakoutFilters) -> None:
    st.markdown("### Compare Tickers")
    filtered = apply_breakout_filters(df, filters)
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
        return

    compare_links = " · ".join(ticker_link_html(symbol) for symbol in picked)
    st.markdown(f"Profiles: {compare_links}", unsafe_allow_html=True)

    compare_data = [get_ticker_by_name(tickers, name) for name in picked]
    compare_data = [item for item in compare_data if item]
    fig = render_compare_radar(compare_data)
    if fig:
        st.plotly_chart(fig, use_container_width=True)

    compare_rows = []
    for ticker_data in compare_data:
        summary = ticker_data.get("summary", {})
        row = {
            "ticker": ticker_data["ticker"],
            "tier": ticker_data["tier"],
            "final_score": summary.get("final_adjusted_score", 0),
            "sector_etf": ticker_data.get("sector_etf"),
        }
        scores = ticker_data.get("scores") or {}
        for key, label in [
            ("rs_market", "RS Mkt"),
            ("rs_sector", "RS Sec"),
            ("compression", "Compress"),
            ("accumulation", "Accum"),
            ("revenue", "Revenue"),
            ("eps", "EPS"),
        ]:
            row[label] = scores.get(key, {}).get("score", 0)
        compare_rows.append(row)

    compare_df = pd.DataFrame(compare_rows)
    st.dataframe(compare_df, use_container_width=True, hide_index=True)
    st.markdown(
        " · ".join(ticker_link_html(symbol) for symbol in compare_df["ticker"]),
        unsafe_allow_html=True,
    )


def render_breakout_header(
    *,
    report_path: str,
    summary: dict,
    regime: dict,
    detail_ticker: str | None,
) -> None:
    render_scan_header(report_path, summary, regime)
    if not detail_ticker:
        return
    link = ticker_link_html(detail_ticker)
    st.markdown(
        f'<div class="info-card">Viewing profile: <strong>{link}</strong> '
        f"— open the <em>Ticker Detail</em> tab or click any ticker link.</div>",
        unsafe_allow_html=True,
    )
