"""Launchpad dashboard tab renderers."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from quant_hub.dashboard.viz.components import (
    get_ticker_by_name,
    render_compare_radar,
    render_scan_header,
    render_ticker_detail,
    tier_badge_html,
)
from quant_hub.dashboard.viz.data import (
    LAUNCHPAD_SCORE_LABELS,
    full_universe_dataframe,
)
from quant_hub.dashboard.viz.labels import tier_friendly
from quant_hub.dashboard.viz.launchpad_filters import (
    LaunchpadFilters,
    apply_launchpad_filters,
)
from quant_hub.dashboard.viz.launchpad_overview import render_launchpad_overview
from quant_hub.dashboard.viz.navigation import (
    set_detail_ticker,
    ticker_link_html,
    ticker_picker_options,
)
from quant_hub.dashboard.viz.styles import PLOTLY_CONFIG
from quant_hub.dashboard.viz.table_helpers import (
    merge_column_config,
    table_column_order,
    with_ticker_links,
)
from quant_hub.dashboard.viz.ticker_history_components import render_ticker_history_panel
from quant_hub.dashboard.viz.universe_panel import (
    apply_universe_controls,
    render_universe_summary,
    universe_display_columns,
    universe_table_column_config,
)
from quant_hub.dashboard.viz.ux_helpers import render_near_miss_panel
from quant_hub.infrastructure.postgres.repository import ScanRepository


def render_overview_tab(
    *,
    summary: dict,
    regime: dict,
    tickers: list[dict],
    repo: ScanRepository | None = None,
    strategy_id: str = "launchpad",
    universe_id: str | None = None,
    scan_date: date | str | None = None,
) -> None:
    render_launchpad_overview(
        summary=summary,
        regime=regime,
        tickers=tickers,
        repo=repo,
        strategy_id=strategy_id,
        universe_id=universe_id,
        scan_date=scan_date,
    )


def render_all_tickers_tab(
    *,
    tickers: list[dict],
    filters: LaunchpadFilters,
    detail_ticker: str | None,
) -> str | None:
    st.markdown("### Full Universe")
    full_df = apply_launchpad_filters(full_universe_dataframe(tickers), filters)
    if full_df.empty:
        st.warning("No tickers match the current filters.")
        return detail_ticker

    render_universe_summary(full_df)
    table_df = apply_universe_controls(full_df)

    display_cols = universe_display_columns(table_df)
    shown_df = with_ticker_links(table_df[display_cols].copy())

    st.dataframe(
        shown_df,
        use_container_width=True,
        hide_index=True,
        key="launchpad_all_tickers_select",
        column_config=universe_table_column_config(),
        column_order=table_column_order(display_cols),
    )
    st.download_button(
        "Download filtered CSV",
        table_df.to_csv(index=False).encode(),
        file_name="launchpad_scan_full.csv",
        mime="text/csv",
    )

    return detail_ticker


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
        options, pick_index = ticker_picker_options(all_symbols, detail_ticker)
        picked = st.selectbox(
            "Select ticker",
            options,
            index=pick_index,
            key="launchpad_detail_tab_pick",
            format_func=lambda value: "Select a ticker..." if value == "" else value,
        )
        if picked and picked != detail_ticker:
            set_detail_ticker(picked)
            active = picked
        else:
            active = detail_ticker or picked or None
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
                f"Finviz: {ticker_link_html(symbol)} {tier_badge_html(row['tier'])}",
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

    compare_df = with_ticker_links(pd.DataFrame(compare_rows))
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
    scan_date: str | None = None,
) -> None:
    render_scan_header(
        report_path,
        summary,
        regime,
        scan_date=scan_date,
        title="Launchpad",
    )
