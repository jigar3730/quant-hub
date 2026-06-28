"""Dashboard sidebar controls — Postgres-backed."""

from __future__ import annotations

from datetime import date

import streamlit as st

from quant_hub.application.universe_service import UniverseService
from quant_hub.dashboard.viz.breakout_filters import BreakoutFilters
from quant_hub.dashboard.viz.navigation import set_detail_ticker, sync_detail_ticker
from quant_hub.dashboard.viz.styles import COMPONENT_HELP
from quant_hub.infrastructure.postgres.repository import ScanRepository


def render_sidebar_controls(
    repo: ScanRepository,
) -> tuple[str, date | None, BreakoutFilters]:
    st.sidebar.title("Quant Hub")

    universes = UniverseService().list_universes()
    universe_id = st.sidebar.selectbox(
        "Universe",
        options=list(universes.keys()),
        format_func=lambda k: f"{k} — {universes[k]}",
    )

    runs = repo.list_runs(limit=30)
    universe_runs = [r for r in runs if r["universe_id"] == universe_id]
    scan_date: date | None = None
    if universe_runs:
        date_options = [str(r["scan_date"]) for r in universe_runs]
        selected = st.sidebar.selectbox("Scan date", options=date_options, index=0)
        scan_date = date.fromisoformat(selected)
    else:
        st.sidebar.caption("No scans for this universe yet.")

    st.sidebar.divider()
    st.sidebar.header("Breakout filters")
    filters = BreakoutFilters(
        tier=st.sidebar.selectbox("Tier", ["All", "Tier 1", "Tier 2", "Tier 3", "filtered"]),
        eligible_only=st.sidebar.checkbox("Eligible only", value=False),
        actionable_only=st.sidebar.checkbox("Actionable only (Tier 1+2)", value=False),
        min_score=st.sidebar.slider("Min final score", 0.0, 100.0, 0.0, 5.0),
        search=st.sidebar.text_input("Search ticker", "").strip().upper(),
    )

    with st.sidebar.expander("Score component guide"):
        for key, text in COMPONENT_HELP.items():
            label = key.replace("_", " ").title()
            st.markdown(f"**{label}** — {text}")

    return universe_id, scan_date, filters


def render_sidebar_ticker_picker(all_symbols: list[str]) -> str | None:
    detail_ticker = sync_detail_ticker()
    st.sidebar.divider()
    st.sidebar.header("Ticker Detail")
    sidebar_pick = st.sidebar.selectbox(
        "Open ticker profile",
        options=[""] + all_symbols,
        index=(all_symbols.index(detail_ticker) + 1) if detail_ticker in all_symbols else 0,
        format_func=lambda value: "Select a ticker..." if value == "" else value,
    )
    if sidebar_pick and sidebar_pick != detail_ticker:
        set_detail_ticker(sidebar_pick)
        detail_ticker = sidebar_pick
    if detail_ticker and st.sidebar.button("Clear ticker selection"):
        set_detail_ticker(None)
        detail_ticker = None
    return detail_ticker
