"""Dashboard sidebar controls — Postgres-backed."""

from __future__ import annotations

from datetime import date

import streamlit as st

from quant_hub.application.universe_service import UniverseService
from quant_hub.dashboard.viz.labels import format_universe_option
from quant_hub.dashboard.viz.launchpad_filters import LaunchpadFilters
from quant_hub.dashboard.viz.launchpad_score_guide import render_launchpad_score_guide
from quant_hub.dashboard.viz.navigation import (
    HISTORY_PAGE_OFFSET_KEY,
    SHOW_GLOBAL_HISTORY_KEY,
    apply_pending_navigation,
    set_detail_ticker,
    sync_detail_ticker,
)
from quant_hub.dashboard.viz.ux_helpers import (
    DASHBOARD_RUN_LOOKUP_LIMIT,
    scanned_universe_ids,
    sorted_universe_ids,
)
from quant_hub.digest import policy as P
from quant_hub.infrastructure.postgres.repository import ScanRepository

STRATEGY_LABELS = {
    "command_center": "Command Center (daily 360°)",
    "launchpad": "Launchpad (daily)",
    "lynch": "Lynch (fundamental)",
    "digest": "Email digests",
}


def _render_global_ticker_lookup() -> None:
    """Omnibar: cross-scan ticker history lookup."""
    st.sidebar.markdown("**Ticker lookup**")
    lookup = st.sidebar.text_input(
        "Lookup ticker history",
        value="",
        key="global_ticker_lookup",
        placeholder="e.g. NVDA",
    ).strip().upper()
    if st.sidebar.button("Search history", key="global_ticker_lookup_btn"):
        if lookup:
            set_detail_ticker(lookup)
            st.session_state[SHOW_GLOBAL_HISTORY_KEY] = True
            st.session_state[f"history_{HISTORY_PAGE_OFFSET_KEY}"] = 0
            st.rerun()
        else:
            st.sidebar.caption("Enter a ticker symbol.")
    st.sidebar.divider()


def _scan_date_index(date_options: list[str], pending: date | None) -> int:
    if pending is None:
        return 0
    pending_s = str(pending)
    return date_options.index(pending_s) if pending_s in date_options else 0


def render_sidebar_controls(
    repo: ScanRepository,
) -> tuple[str, str, date | None, LaunchpadFilters]:
    pending_scan_date = apply_pending_navigation()
    st.sidebar.title("Quant Hub")
    _render_global_ticker_lookup()

    if "sidebar_strategy" not in st.session_state:
        st.session_state["sidebar_strategy"] = "launchpad"

    strategy_id = st.sidebar.selectbox(
        "Strategy",
        options=list(STRATEGY_LABELS.keys()),
        format_func=lambda k: STRATEGY_LABELS[k],
        key="sidebar_strategy",
    )

    if strategy_id == "command_center":
        scan_dates = repo.list_scan_dates(limit=DASHBOARD_RUN_LOOKUP_LIMIT)
        scan_date: date | None = None
        if scan_dates:
            date_options = [str(d) for d in scan_dates]
            selected = st.sidebar.selectbox(
                "Scan date",
                options=date_options,
                index=_scan_date_index(date_options, pending_scan_date),
            )
            scan_date = date.fromisoformat(selected)
        else:
            st.sidebar.caption("No scans recorded yet.")
        st.sidebar.caption("Cross-scanner 360° rollup for the selected date.")
        return strategy_id, "__all__", scan_date, LaunchpadFilters()

    if strategy_id == "digest":
        digest_kind = st.sidebar.selectbox(
            "Digest type",
            options=["daily", "weekly"],
            format_func=lambda k: "Daily Launchpad brief" if k == "daily" else "Weekly Lynch digest",
            key="digest_kind",
        )
        lookup_strategy = "launchpad" if digest_kind == "daily" else "lynch"
        lookup_universe = (
            P.DAILY_LAUNCHPAD_UNIVERSE if digest_kind == "daily" else P.WEEKLY_LYNCH_UNIVERSE
        )
        runs = repo.list_runs(
            strategy_id=lookup_strategy,
            limit=DASHBOARD_RUN_LOOKUP_LIMIT,
            exclude_fixtures=True,
        )
        universe_runs = [r for r in runs if r["universe_id"] == lookup_universe]
        scan_date: date | None = None
        if universe_runs:
            date_options = [str(r["scan_date"]) for r in universe_runs]
            selected = st.sidebar.selectbox(
                "Digest date",
                options=date_options,
                index=_scan_date_index(date_options, pending_scan_date),
            )
            scan_date = date.fromisoformat(selected)
        else:
            st.sidebar.caption("No scans available for this digest yet.")
        st.sidebar.caption("Preview matches scheduled `quant-digest` emails.")
        return strategy_id, lookup_universe, scan_date, LaunchpadFilters()

    universes = UniverseService().list_universes()
    scanned = scanned_universe_ids(repo, strategy_id)
    universe_options = sorted_universe_ids(list(universes.keys()), scanned)

    if "sidebar_universe" not in st.session_state:
        st.session_state["sidebar_universe"] = (
            next((u for u in universe_options if u in scanned), universe_options[0])
        )
    if st.session_state["sidebar_universe"] not in universe_options:
        st.session_state["sidebar_universe"] = universe_options[0]

    universe_id = st.sidebar.selectbox(
        "Universe",
        options=universe_options,
        format_func=lambda k: format_universe_option(k, universes[k], has_scan=k in scanned),
        key="sidebar_universe",
    )

    runs = repo.list_runs(
        strategy_id=strategy_id,
        limit=DASHBOARD_RUN_LOOKUP_LIMIT,
        exclude_fixtures=True,
    )
    universe_runs = [r for r in runs if r["universe_id"] == universe_id]
    scan_date: date | None = None
    if universe_runs:
        date_options = [str(r["scan_date"]) for r in universe_runs]
        selected = st.sidebar.selectbox(
            "Scan date",
            options=date_options,
            index=_scan_date_index(date_options, pending_scan_date),
        )
        scan_date = date.fromisoformat(selected)
    else:
        st.sidebar.caption("No scans for this universe yet.")

    st.sidebar.divider()

    if strategy_id == "lynch":
        st.sidebar.header("Lynch filters")
        filters = LaunchpadFilters(
            tier="All",
            eligible_only=False,
            actionable_only=st.sidebar.checkbox("Passed only", value=False),
            min_score=0.0,
            search=st.sidebar.text_input("Search ticker", "").strip().upper(),
        )
    elif strategy_id == "launchpad":
        st.sidebar.header("Launchpad filters")
        actionable_only = st.sidebar.checkbox("Actionable only (Tier 1+2)", value=False)
        min_label = (
            "Min normalized score (tier threshold)"
            if actionable_only
            else "Min normalized score"
        )
        filters = LaunchpadFilters(
            tier=st.sidebar.selectbox("Tier", ["All", "Tier 1", "Tier 2", "Tier 3", "filtered"]),
            eligible_only=st.sidebar.checkbox("Eligible only", value=False),
            actionable_only=actionable_only,
            min_score=st.sidebar.slider(min_label, 0.0, 100.0, 0.0, 5.0),
            search=st.sidebar.text_input("Search ticker", "").strip().upper(),
        )
        with st.sidebar.expander("Launchpad rubric cheat sheet", expanded=False):
            render_launchpad_score_guide(in_sidebar=True)

    return strategy_id, universe_id, scan_date, filters


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
        from quant_hub.dashboard.viz.navigation import set_detail_ticker

        set_detail_ticker(sidebar_pick)
        detail_ticker = sidebar_pick
    if detail_ticker and st.sidebar.button("Clear ticker selection"):
        from quant_hub.dashboard.viz.navigation import set_detail_ticker

        set_detail_ticker(None)
        detail_ticker = None
    return detail_ticker
