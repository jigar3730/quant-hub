"""Swing dashboard tab renderers."""

from __future__ import annotations

import streamlit as st

from quant_hub.dashboard.viz.swing_filters import SwingFilters, apply_swing_filters, swing_setups_dataframe


def render_swing_header(summary: dict, regime: dict, report_label: str) -> None:
    longs = summary.get("setup_long_count", summary["tier_counts"].get("SETUP_LONG", 0))
    shorts = summary.get("setup_short_count", summary["tier_counts"].get("SETUP_SHORT", 0))
    st.markdown(
        f"""
        <div class="scan-header">
            <h1>Swing Setup Scanner</h1>
            <p>
              {summary['universe_size']} tickers scanned
              &nbsp;|&nbsp; {summary['eligible_count']} setups found
              &nbsp;|&nbsp; {longs} long &nbsp;|&nbsp; {shorts} short
              &nbsp;|&nbsp; Weekly ({regime.get('period', '10y')} / {regime.get('interval', '1wk')})
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Report: `{report_label}`")


def render_swing_setups_tab(tickers: list[dict], filters: SwingFilters) -> None:
    st.markdown("### Weekly Setups")
    df = apply_swing_filters(swing_setups_dataframe(tickers), filters)
    if df.empty:
        st.info("No swing setups match the current filters.")
        return
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ticker": st.column_config.TextColumn("Symbol"),
            "setup_type": st.column_config.TextColumn("Setup"),
            "close": st.column_config.NumberColumn("Close", format="%.2f"),
            "rsi": st.column_config.NumberColumn("RSI", format="%.1f"),
            "ema20": st.column_config.NumberColumn("EMA20", format="%.2f"),
            "ema50": st.column_config.NumberColumn("EMA50", format="%.2f"),
            "atr": st.column_config.NumberColumn("ATR", format="%.2f"),
            "notes": st.column_config.TextColumn("Notes"),
        },
    )
