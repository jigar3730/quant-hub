"""Streamlit dashboard — loads scan results from Postgres."""

from __future__ import annotations

import streamlit as st

from quant_hub.dashboard.viz.data import tickers_to_dataframe
from quant_hub.dashboard.viz.labels import format_report_label
from quant_hub.dashboard.viz.lynch_components import render_lynch_tab
from quant_hub.dashboard.viz.navigation import sync_detail_ticker
from quant_hub.dashboard.viz.pages.breakout import (
    render_all_tickers_tab,
    render_breakout_header,
    render_compare_tab,
    render_overview_tab,
    render_ticker_detail_tab,
    render_watchlist_tab,
)
from quant_hub.dashboard.viz.pages.swing import (
    render_swing_detail_tab,
    render_swing_header,
    render_swing_rejection_tab,
    render_swing_setups_tab,
    render_swing_universe_tab,
)
from quant_hub.dashboard.viz.sidebar import render_sidebar_controls, render_sidebar_ticker_picker
from quant_hub.dashboard.viz.styles import CUSTOM_CSS
from quant_hub.dashboard.viz.swing_filters import SwingFilters
from quant_hub.dashboard.viz.ux_helpers import render_disclaimer, render_scan_provenance_footer
from quant_hub.infrastructure.postgres.connection import ping
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository

st.set_page_config(
    page_title="Quant Hub",
    page_icon="QH",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def _render_system_panel(job_repo: JobRunRepository, repo: ScanRepository) -> None:
    st.subheader("System Status")
    counts = repo.table_counts()
    c1, c2, c3 = st.columns(3)
    c1.metric("Scan runs", counts.get("scan_runs", 0))
    c2.metric("Ticker results", counts.get("ticker_results", 0))
    c3.metric("Job runs", counts.get("job_runs", 0))

    st.markdown("**Recent jobs**")
    jobs = job_repo.recent_jobs(limit=8)
    if jobs:
        for job in jobs:
            st.text(
                f"{job['job_name']} status={job['status']} "
                f"fetched={job.get('tickers_fetched', 0)}/"
                f"{job.get('tickers_requested', 0)}"
            )
    else:
        st.caption("No jobs recorded yet.")

    st.markdown("**Recent scans (breakout)**")
    for run in repo.list_runs(strategy_id="breakout", limit=8, exclude_fixtures=True):
        st.text(
            f"{run['scan_date']} {run['universe_id']} "
            f"T1={run.get('tier1_count', 0)} T2={run.get('tier2_count', 0)} "
            f"actionable={run.get('actionable_count', 0)}"
        )

    st.markdown("**Recent scans (swing)**")
    for run in repo.list_runs(strategy_id="swing", limit=5, exclude_fixtures=True):
        st.text(
            f"{run['scan_date']} {run['universe_id']} "
            f"long={run.get('tier1_count', 0)} short={run.get('tier2_count', 0)}"
        )

    st.markdown("**Recent scans (lynch)**")
    for run in repo.list_runs(strategy_id="lynch", limit=5, exclude_fixtures=True):
        st.text(
            f"{run['scan_date']} {run['universe_id']} "
            f"passed={run.get('actionable_count', 0)} "
            f"FG={run.get('tier1_count', 0)} ST={run.get('tier2_count', 0)} AP={run.get('tier3_count', 0)}"
        )


repo = ScanRepository()
job_repo = JobRunRepository()

if not ping():
    st.error("Cannot connect to Postgres. Check DATABASE_URL and that the database is running.")
    st.stop()

strategy_id, universe_id, scan_date, filters = render_sidebar_controls(repo)

report = repo.load_report(
    strategy_id=strategy_id,
    universe_id=universe_id,
    scan_date=scan_date,
    exclude_fixtures=scan_date is None,
)
if report is None:
    st.warning("No scan found for this strategy/universe/date.")
    st.info(
        "Run `quant-scan --universe sp500 --cache`, `quant-swing --universe sp500`, "
        "`quant-lynch --universe sp500`, or wait for scheduled cron jobs."
    )
    with st.expander("System status"):
        _render_system_panel(job_repo, repo)
    st.stop()

regime = report["market_regime"]
summary = report["scan_summary"]
tickers = report["tickers"]
df = tickers_to_dataframe(tickers)
all_symbols = sorted(df["ticker"].tolist())
scan_date_str = str(report.get("scan_date", scan_date or ""))
report_label = format_report_label(
    strategy_id=strategy_id,
    universe_id=universe_id,
    scan_date=scan_date_str,
)
provenance = report.get("data_provenance")

detail_ticker = render_sidebar_ticker_picker(all_symbols) if all_symbols else sync_detail_ticker()

if strategy_id == "swing":
    render_swing_header(summary, regime, report_label, scan_date=scan_date_str)
    render_scan_provenance_footer(
        strategy_id=strategy_id,
        universe_id=universe_id,
        scan_date=scan_date_str,
        provenance=provenance,
    )
    tab_names = ["Setups", "Full Universe", "Ticker Detail", "Rejection Breakdown"]
    tabs = st.tabs(tab_names)
    tab_map = dict(zip(tab_names, tabs, strict=True))
    assert isinstance(filters, SwingFilters)
    with tab_map["Setups"]:
        render_swing_setups_tab(
            tickers,
            filters,
            summary=summary,
            repo=repo,
            universe_id=universe_id,
            scan_date=scan_date,
        )
    with tab_map["Full Universe"]:
        detail_ticker = render_swing_universe_tab(
            tickers,
            filters,
            detail_ticker=detail_ticker,
        )
    with tab_map["Ticker Detail"]:
        render_swing_detail_tab(tickers, all_symbols, detail_ticker)
    with tab_map["Rejection Breakdown"]:
        render_swing_rejection_tab(summary)
    with st.expander("System status (admin)"):
        _render_system_panel(job_repo, repo)
    render_disclaimer()
    st.stop()

if strategy_id == "lynch":
    render_lynch_tab(report, report_label)
    render_scan_provenance_footer(
        strategy_id=strategy_id,
        universe_id=universe_id,
        scan_date=scan_date_str,
        provenance=provenance,
    )
    with st.expander("System status (admin)"):
        _render_system_panel(job_repo, repo)
    render_disclaimer()
    st.stop()

render_breakout_header(
    report_path=report_label,
    summary=summary,
    regime=regime,
    detail_ticker=detail_ticker,
    scan_date=scan_date_str,
)
render_scan_provenance_footer(
    strategy_id=strategy_id,
    universe_id=universe_id,
    scan_date=scan_date_str,
    provenance=provenance,
)

tab_names = ["Overview", "Full Universe", "Ticker Detail", "Actionable Watchlist", "Compare"]
tabs = st.tabs(tab_names)
tab_map = dict(zip(tab_names, tabs, strict=True))

with tab_map["Overview"]:
    render_overview_tab(
        report_path=report_label,
        summary=summary,
        regime=regime,
        df=df,
        tickers=tickers,
        filters=filters,
        repo=repo,
        universe_id=universe_id,
        scan_date=scan_date,
    )

with tab_map["Full Universe"]:
    detail_ticker = render_all_tickers_tab(
        tickers=tickers,
        filters=filters,
        detail_ticker=detail_ticker,
    )

with tab_map["Ticker Detail"]:
    render_ticker_detail_tab(
        tickers=tickers,
        all_symbols=all_symbols,
        detail_ticker=detail_ticker,
        scan_date=scan_date_str,
    )

with tab_map["Actionable Watchlist"]:
    render_watchlist_tab(
        df=df,
        tickers=tickers,
        filters=filters,
        repo=repo,
        universe_id=universe_id,
        scan_date=scan_date,
        summary=summary,
        regime=regime,
    )

with tab_map["Compare"]:
    render_compare_tab(df=df, tickers=tickers, filters=filters)

with st.expander("System status (admin)"):
    _render_system_panel(job_repo, repo)

render_disclaimer()
