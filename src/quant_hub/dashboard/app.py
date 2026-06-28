"""Streamlit dashboard — loads scan results from Postgres."""

from __future__ import annotations

import streamlit as st

from quant_hub.dashboard.viz.data import tickers_to_dataframe
from quant_hub.dashboard.viz.navigation import sync_detail_ticker
from quant_hub.dashboard.viz.pages.breakout import (
    render_all_tickers_tab,
    render_breakout_header,
    render_compare_tab,
    render_overview_tab,
    render_ticker_detail_tab,
    render_watchlist_tab,
)
from quant_hub.dashboard.viz.sidebar import render_sidebar_controls, render_sidebar_ticker_picker
from quant_hub.dashboard.viz.styles import CUSTOM_CSS
from quant_hub.infrastructure.postgres.connection import ping
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository

st.set_page_config(
    page_title="Quant Hub",
    page_icon="QH",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def _render_system_panel(job_repo: JobRunRepository, repo: ScanRepository) -> None:
    st.subheader("System Status")
    counts = repo.table_counts()
    c1, c2, c3 = st.columns(3)
    c1.metric("Scan runs", counts.get("scan_runs", 0))
    c2.metric("Ticker results", counts.get("ticker_results", 0))
    c3.metric("Job runs", counts.get("job_runs", 0))

    job = job_repo.latest_job()
    if job:
        st.markdown("**Latest job**")
        st.json(
            {
                "name": job["job_name"],
                "status": job["status"],
                "started": str(job["started_at"]),
                "finished": str(job.get("finished_at")),
                "requested": job.get("tickers_requested"),
                "fetched": job.get("tickers_fetched"),
                "failed": job.get("tickers_failed"),
            }
        )

    st.markdown("**Recent scans**")
    for run in repo.list_runs(limit=10):
        st.text(
            f"{run['scan_date']} {run['universe_id']} "
            f"T1={run.get('tier1_count', 0)} T2={run.get('tier2_count', 0)} "
            f"actionable={run.get('actionable_count', 0)}"
        )


repo = ScanRepository()
job_repo = JobRunRepository()

if not ping():
    st.error("Cannot connect to Postgres. Check DATABASE_URL and that the database is running.")
    st.stop()

universe_id, scan_date, filters = render_sidebar_controls(repo)

report = repo.load_report(universe_id=universe_id, scan_date=scan_date)
if report is None:
    st.warning("No scan found for this universe/date.")
    st.info("Run `quant-scan --universe sp500 --cache` or wait for the daily cron job.")
    with st.expander("System status"):
        _render_system_panel(job_repo, repo)
    st.stop()

regime = report["market_regime"]
summary = report["scan_summary"]
tickers = report["tickers"]
df = tickers_to_dataframe(tickers)
all_symbols = sorted(df["ticker"].tolist())
report_label = f"{universe_id} — {report.get('scan_date', 'latest')}"

detail_ticker = render_sidebar_ticker_picker(all_symbols) if all_symbols else sync_detail_ticker()

render_breakout_header(
    report_path=report_label,
    summary=summary,
    regime=regime,
    detail_ticker=detail_ticker,
)

tab_names = ["Overview", "Full Universe", "Ticker Detail", "Actionable Watchlist", "Compare", "System"]
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
        detail_ticker=detail_ticker,
        filters=filters,
    )

with tab_map["Actionable Watchlist"]:
    render_watchlist_tab(tickers=tickers, filters=filters)

with tab_map["Compare"]:
    render_compare_tab(tickers=tickers, filters=filters)

with tab_map["System"]:
    _render_system_panel(job_repo, repo)
