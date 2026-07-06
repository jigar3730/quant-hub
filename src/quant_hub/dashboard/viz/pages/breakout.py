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
from quant_hub.dashboard.viz.labels import tier_friendly
from quant_hub.dashboard.viz.navigation import (
    dashboard_ticker_link_html,
    set_detail_ticker,
    ticker_link_html,
)
from quant_hub.dashboard.viz.ticker_history_components import render_ticker_history_panel
from quant_hub.infrastructure.postgres.repository import ScanRepository
from quant_hub.dashboard.viz.signals import render_signal_insights_panel, signal_insights
from quant_hub.dashboard.viz.styles import PLOTLY_CONFIG
from quant_hub.dashboard.viz.table_helpers import (
    merge_column_config,
    table_column_order,
    with_yahoo_ticker_links,
)
from quant_hub.dashboard.viz.universe_panel import (
    apply_universe_controls,
    render_universe_detail_panel,
    render_universe_summary,
    universe_display_columns,
    universe_table_column_config,
)
from quant_hub.dashboard.viz.ux_helpers import render_breakout_takeaway, render_near_miss_panel
from quant_hub.infrastructure.postgres.repository import ScanRepository


def render_overview_tab(
    *,
    report_path: str,
    summary: dict,
    regime: dict,
    df: pd.DataFrame,
    tickers: list[dict],
    filters: BreakoutFilters,
    repo: ScanRepository,
    universe_id: str,
    scan_date,
) -> None:
    render_breakout_takeaway(
        summary=summary,
        regime=regime,
        df=df,
        repo=repo,
        universe_id=universe_id,
        scan_date=scan_date,
        key_prefix="overview",
    )
    render_regime_panel(regime)

    fq = summary.get("fundamentals_quality")
    if fq and fq.get("tickers"):
        with st.expander("Fundamentals data quality", expanded=False):
            c1, c2, c3 = st.columns(3)
            eps = fq.get("eps", {})
            rev = fq.get("revenue", {})
            c1.metric("EPS coverage", f"{eps.get('ok_pct', 0)}%")
            c2.metric("Revenue coverage", f"{rev.get('ok_pct', 0)}%")
            c3.metric("Avg quarters", fq.get("avg_quarters", 0))

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

    filtered_df = apply_breakout_filters(df, filters)
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
        )
        if len(heat_df) > 1:
            st.plotly_chart(render_heatmap(heat_df), use_container_width=True, config=PLOTLY_CONFIG)

    scatter_df = scatter_dataframe(
        [t for t in tickers if t["ticker"] in set(eligible_df["ticker"])]
    )
    if scatter_df.empty:
        return

    st.caption("Chart labels show tickers — use the Yahoo Finance links below for live quotes.")
    st.plotly_chart(render_scatter(scatter_df), use_container_width=True, config=PLOTLY_CONFIG)
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
    shown_df = with_yahoo_ticker_links(table_df[display_cols].copy())

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
            column_order=table_column_order(display_cols),
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
    scan_date: str | None = None,
    repo: ScanRepository | None = None,
) -> None:
    st.markdown("### Ticker Profile")
    st.caption("Fundamentals, technical scores, eligibility checks, and news.")

    active = detail_ticker
    if all_symbols:
        pick_index = all_symbols.index(detail_ticker) if detail_ticker in all_symbols else 0
        active = st.selectbox(
            "Select ticker",
            all_symbols,
            index=pick_index,
            key="detail_tab_pick",
        )
        if active != detail_ticker:
            set_detail_ticker(active)
    elif detail_ticker:
        active = detail_ticker
        st.markdown(f"**{detail_ticker}** — not in this scan's universe.")
    else:
        st.info("Select a ticker from the sidebar lookup or universe table.")
        return

    ticker_data = get_ticker_by_name(tickers, active) if active else None
    if ticker_data:
        render_ticker_detail(active, ticker_data, scan_date=scan_date, repo=repo)
    elif active and repo is not None:
        render_ticker_history_panel(repo, active, key_prefix="breakout_orphan")
    elif active:
        st.warning(f"No data for {active} in this scan.")


def render_watchlist_tab(
    *,
    df: pd.DataFrame,
    tickers: list[dict],
    filters: BreakoutFilters,
    repo: ScanRepository | None = None,
    universe_id: str = "",
    scan_date=None,
    summary: dict | None = None,
    regime: dict | None = None,
) -> None:
    st.markdown("### High conviction & watchlist — actionable candidates")
    actionable = apply_breakout_filters(df, filters)
    actionable = actionable[actionable["tier"].isin(["Tier 1", "Tier 2"])].sort_values(
        "final_score",
        ascending=False,
    )
    if actionable.empty:
        st.warning(
            "No high-conviction or watchlist names in this scan. "
            "See near-miss names below or use the Overview tab for cross-strategy links."
        )
        if summary and regime and repo:
            render_breakout_takeaway(
                summary=summary,
                regime=regime,
                df=df,
                repo=repo,
                universe_id=universe_id,
                scan_date=scan_date,
                key_prefix="watchlist",
            )
        else:
            render_near_miss_panel(df)
        return

    st.download_button(
        "Download watchlist CSV",
        actionable.to_csv(index=False).encode(),
        file_name="breakout_watchlist.csv",
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
            st.caption(
                f"{ticker_data.get('tier_reason', '')} "
                "Open the **Ticker Detail** tab for full scan profile, scores, and news."
            )
            cols = st.columns(4)
            cols[0].metric("Final Score", f"{row['final_score']:.1f}")
            cols[1].metric("Universe Rank", f"{row['normalized_score']:.1f}")
            cols[2].metric("Sector ETF", row.get("sector_etf") or "—")
            scores = ticker_data.get("scores") or {}
            if scores:
                insights = signal_insights(ticker_data)
                cols[3].metric(
                    "Top signals",
                    insights["top_short"].split(" · ")[0],
                    help=insights["top_tooltip"],
                )
                with st.expander(f"{symbol} — signal readout", expanded=False):
                    render_signal_insights_panel(ticker_data)


def render_compare_tab(*, df: pd.DataFrame, tickers: list[dict], filters: BreakoutFilters) -> None:
    st.markdown("### Compare Tickers")
    filtered = apply_breakout_filters(df, filters)
    eligible_names = (
        filtered[filtered["eligible"]]
        .sort_values("final_score", ascending=False)["ticker"]
        .tolist()
    )
    actionable_names = (
        filtered[filtered["tier"].isin(["Tier 1", "Tier 2"])]
        .sort_values("final_score", ascending=False)["ticker"]
        .tolist()
    )
    if len(eligible_names) < 2:
        st.warning("Need at least 2 eligible tickers to compare.")
        return

    if len(actionable_names) >= 2:
        default_pick = actionable_names[: min(3, len(actionable_names))]
        st.caption("Default selection: high-conviction / watchlist names only.")
    else:
        default_pick = []
        st.caption("No actionable pair — select eligible tickers manually.")

    picked = st.multiselect(
        "Select 2–3 tickers",
        eligible_names,
        default=default_pick,
        max_selections=3,
    )
    if len(picked) < 2:
        st.info("Select at least 2 tickers to compare.")
        return

    compare_links = " · ".join(ticker_link_html(symbol) for symbol in picked)
    st.markdown(f"Profiles: {compare_links}", unsafe_allow_html=True)

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
    scan_date: str | None = None,
) -> None:
    render_scan_header(report_path, summary, regime, scan_date=scan_date)
    if not detail_ticker:
        return
    link = dashboard_ticker_link_html(detail_ticker)
    st.markdown(
        f'<div class="info-card">Viewing profile: <strong>{link}</strong> '
        f"— open the <em>Ticker Detail</em> tab for the full scan breakdown.</div>",
        unsafe_allow_html=True,
    )
