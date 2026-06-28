"""Peter Lynch dashboard components."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_hub.history.duckdb_store import get_lynch_ticker_history
from quant_hub.lynch.categories import QUALITATIVE_OVERLAY
from quant_hub.dashboard.viz.components import apply_chart_style
from quant_hub.dashboard.viz.styles import PLOTLY_CONFIG
from quant_hub.dashboard.viz.ux_helpers import render_lynch_takeaway
from quant_hub.dashboard.viz.display import format_display_value
from quant_hub.dashboard.viz.lynch_data import (
    CATEGORY_COLORS,
    lynch_checks_dataframe,
    lynch_tickers_to_dataframe,
)
from quant_hub.dashboard.viz.navigation import ticker_link_html
from quant_hub.dashboard.viz.table_helpers import merge_column_config, table_column_order, with_yahoo_ticker_links


def render_lynch_header(report_path: str, summary: dict) -> None:
    cats = summary["category_counts"]
    mq = summary.get("metrics_quality") or {}
    fetch_pct = mq.get("fetch_ok_pct")
    fetch_banner = ""
    if fetch_pct is not None and fetch_pct < 90:
        errors = mq.get("fetch_errors", 0)
        fetch_banner = (
            f"<p style='color:#fca5a5;margin-top:0.5rem'>"
            f"⚠ Data fetch: only {fetch_pct}% of tickers loaded from Yahoo "
            f"({errors} failed). Scores showing blank or 0 are unreliable — re-run the scan."
            f"</p>"
        )
    st.markdown(
        f"""
        <div class="scan-header">
            <h1>Peter Lynch Scanner</h1>
            <p>
              Preset: <strong>{summary['preset_label']}</strong>
              &nbsp;|&nbsp; {summary['universe_size']} tickers scanned
              &nbsp;|&nbsp; {summary['passed_count']} passed
              &nbsp;|&nbsp; Fast growers: {cats['fast_grower']}
              &nbsp;|&nbsp; Stalwarts: {cats['stalwart']}
              &nbsp;|&nbsp; Asset plays: {cats['asset_play']}
            </p>
            {fetch_banner}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Report: {report_path}")


def render_category_chart(category_counts: dict) -> go.Figure:
    labels = ["Fast Grower", "Stalwart", "Asset Play"]
    keys = ["fast_grower", "stalwart", "asset_play"]
    values = [category_counts.get(k, 0) for k in keys]
    colors = [CATEGORY_COLORS[k] for k in keys]
    fig = go.Figure(go.Bar(x=labels, y=values, marker_color=colors))
    fig.update_layout(title="Lynch Category Matches", height=320, yaxis_title="Count")
    return apply_chart_style(fig)


def render_lynch_score_histogram(df: pd.DataFrame) -> go.Figure:
    passed_df = df[df["passed"]]
    fig = go.Figure(go.Histogram(x=passed_df["lynch_score"], nbinsx=20, marker_color="#22c55e"))
    fig.update_layout(title="Lynch Score Distribution (passed)", height=280, xaxis_title="Score")
    return apply_chart_style(fig)


def render_lynch_history_chart(ticker: str) -> go.Figure | None:
    history = get_lynch_ticker_history(ticker)
    if len(history) < 2:
        return None
    hist_df = pd.DataFrame(history).sort_values("scan_date")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=hist_df["scan_date"],
            y=hist_df["lynch_score"],
            mode="lines+markers",
            name="Lynch score",
            line=dict(color="#22c55e"),
        )
    )
    fig.update_layout(
        title=f"{ticker} Lynch score history",
        height=280,
        xaxis_title="Scan date",
        yaxis_title="Score",
    )
    return apply_chart_style(fig)


def _lynch_table_columns() -> dict:
    return merge_column_config({
        "company_name": st.column_config.TextColumn("Company"),
        "sector": st.column_config.TextColumn("Sector"),
        "passed": st.column_config.CheckboxColumn("Passed"),
        "categories": st.column_config.TextColumn("Categories"),
        "lynch_score": st.column_config.NumberColumn(
            "Lynch Score",
            format="%.1f",
            help="Percent of checks passed. Blank means data was not loaded — not a score of zero.",
        ),
        "data_status": st.column_config.TextColumn(
            "Data",
            help="ok = Yahoo fundamentals loaded; unavailable = fetch failed.",
        ),
        "pe_ratio": st.column_config.NumberColumn("P/E", format="%.1f"),
        "peg_ratio": st.column_config.NumberColumn("PEG", format="%.2f"),
        "eps_growth_5y_pct": st.column_config.NumberColumn("EPS Gr 5Y %", format="%.1f"),
        "tier_reason": st.column_config.TextColumn("Tier note", width="medium"),
        "fail_reason": st.column_config.TextColumn("Fail reason", width="medium"),
    })


def _render_lynch_table(table_df: pd.DataFrame) -> None:
    display_df = with_yahoo_ticker_links(table_df)
    base_cols = [column for column in display_df.columns if column != "ticker_link"]
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config=_lynch_table_columns(),
        column_order=table_column_order(base_cols),
    )


def get_lynch_ticker_by_name(tickers: list[dict], symbol: str) -> dict | None:
    symbol = symbol.upper()
    for t in tickers:
        if t.get("ticker", "").upper() == symbol:
            return t
    return None

    symbol = symbol.upper()
    for t in tickers:
        if t.get("ticker", "").upper() == symbol:
            return t
    return None


def render_lynch_ticker_detail(ticker: str, data: dict) -> None:
    st.markdown(f"### {ticker_link_html(ticker)}", unsafe_allow_html=True)
    if data.get("company_name"):
        st.caption(f"{data['company_name']} · {data.get('sector') or '—'}")

    if (data.get("metrics") or {}).get("error"):
        st.error(
            "Fundamental data could not be loaded for this ticker (Yahoo fetch failed). "
            "The Lynch score is unavailable — not a real zero."
        )

    score = data.get("lynch_score")
    cols = st.columns(5)
    cols[0].metric("Lynch Score", "—" if score is None else f"{score:.0f}")
    cols[1].metric("P/E", _fmt_num(data.get("pe_ratio")))
    cols[2].metric("PEG", _fmt_num(data.get("peg_ratio")))
    cols[3].metric("EPS Gr 5Y", _fmt_pct(data.get("eps_growth_5y_pct")))
    cols[4].metric("Passed", "Yes" if data.get("passed") else "No")

    cats = data.get("categories") or []
    if cats:
        cat_labels = ", ".join(c.replace("_", " ").title() for c in cats)
        st.markdown(f"**Categories:** {cat_labels}")
    if data.get("tier_reason"):
        st.info(data["tier_reason"])
    elif data.get("fail_reason"):
        st.warning(data["fail_reason"])

    if data.get("investor_summary"):
        st.markdown("#### In plain English")
        st.write(data["investor_summary"])

    snapshot = data.get("fundamental_snapshot") or []
    if snapshot:
        st.markdown("#### Key fundamentals (what the numbers mean)")
        snap_df = pd.DataFrame(snapshot)
        show_cols = ["label", "display", "explanation", "source"]
        cols_present = [c for c in show_cols if c in snap_df.columns]
        st.dataframe(
            snap_df[cols_present],
            use_container_width=True,
            hide_index=True,
            column_config={
                "label": st.column_config.TextColumn("Metric"),
                "display": st.column_config.TextColumn("Value"),
                "explanation": st.column_config.TextColumn("What it means"),
                "source": st.column_config.TextColumn("Source"),
            },
        )

    hist_fig = render_lynch_history_chart(ticker)
    if hist_fig:
        st.plotly_chart(hist_fig, use_container_width=True, config=PLOTLY_CONFIG)

    checks_df = lynch_checks_dataframe(data)
    if not checks_df.empty:
        st.markdown("#### Quantitative checks")
        st.dataframe(
            checks_df,
            use_container_width=True,
            hide_index=True,
            column_config={"passed": st.column_config.CheckboxColumn("Passed")},
        )

    metrics = data.get("metrics") or {}
    if metrics:
        with st.expander("Raw metrics", expanded=False):
            metric_rows = [
                {"metric": k, "value": format_display_value(v)}
                for k, v in sorted(metrics.items())
                if k not in ("ticker", "company_name", "sector")
            ]
            st.dataframe(pd.DataFrame(metric_rows), use_container_width=True, hide_index=True)


def render_lynch_tab(report: dict, report_path: str) -> None:
    summary = report["scan_summary"]
    tickers = report["tickers"]
    candidates = report.get("candidates", [])
    df = lynch_tickers_to_dataframe(tickers)

    render_lynch_header(report_path, summary)

    sub_candidates, sub_overview, sub_all, sub_detail = st.tabs(
        ["Candidates", "Overview", "All Tickers", "Ticker Detail"]
    )

    with sub_candidates:
        render_lynch_takeaway(summary=summary, candidate_count=len(candidates))
        st.markdown("### Top Lynch Candidates")
        if not candidates:
            st.warning("No candidates passed the screen for this preset.")
        else:
            cand_df = lynch_tickers_to_dataframe(candidates)
            st.download_button(
                "Download candidates CSV",
                cand_df.to_csv(index=False).encode(),
                file_name="lynch_candidates.csv",
                mime="text/csv",
                key="lynch_candidates_csv",
            )
            _render_lynch_table(cand_df)
            for t in candidates[:15]:
                with st.expander(
                    f"{t['ticker']} — score {t.get('lynch_score', 0):.0f}",
                    expanded=len(candidates) <= 3,
                ):
                    render_lynch_ticker_detail(t["ticker"], t)

    with sub_overview:
        mq = summary.get("metrics_quality")
        if mq:
            with st.expander("Data quality (Yahoo Finance feed)", expanded=False):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Fetch success", f"{mq.get('fetch_ok_pct', 0)}%")
                c2.metric("Complete profiles", f"{mq.get('data_complete_pct', 0)}%")
                c3.metric("Missing PEG", mq.get("missing_peg", 0))
                c4.metric("Fetch errors", mq.get("fetch_errors", 0))
                prov = report.get("data_provenance") or {}
                if prov:
                    st.caption(
                        f"Source: {prov.get('price_source', 'yfinance')} · "
                        f"Scan: {prov.get('scan_date', '—')} · "
                        f"Universe: {prov.get('universe_id', '—')}"
                    )

        c1, c2 = st.columns(2)
        with c1:
            category_fig = render_category_chart(summary["category_counts"])
            st.plotly_chart(category_fig, use_container_width=True, config=PLOTLY_CONFIG)
        with c2:
            if df[df["passed"]].empty:
                st.info("No tickers passed the Lynch screen in this run.")
            else:
                st.plotly_chart(
                    render_lynch_score_histogram(df),
                    use_container_width=True,
                    config=PLOTLY_CONFIG,
                )

        st.markdown("#### Qualitative overlay (manual review)")
        for note in report.get("qualitative_overlay") or QUALITATIVE_OVERLAY:
            st.markdown(f"- {note}")

    with sub_all:
        st.markdown("### Full Universe")
        col_f1, col_f2, col_f3 = st.columns(3)
        passed_only = col_f1.checkbox("Passed only", value=False, key="lynch_passed_only")
        cat_filter = col_f2.selectbox(
            "Category",
            ["All", "fast_grower", "stalwart", "asset_play", "base"],
            key="lynch_cat_filter",
        )
        search = col_f3.text_input("Search ticker", "", key="lynch_search").strip().upper()

        table_df = df.copy()
        if passed_only:
            table_df = table_df[table_df["passed"]]
        if cat_filter != "All":
            if cat_filter == "base":
                table_df = table_df[table_df["categories"] == "base"]
            else:
                table_df = table_df[table_df["categories"].str.contains(cat_filter, na=False)]
        if search:
            table_df = table_df[table_df["ticker"].str.contains(search, na=False)]

        _render_lynch_table(table_df)
        st.download_button(
            "Download CSV",
            table_df.to_csv(index=False).encode(),
            file_name="lynch_scan_results.csv",
            mime="text/csv",
            key="lynch_csv_download",
        )

    with sub_detail:
        symbols = sorted(df["ticker"].tolist())
        if not symbols:
            st.warning("No tickers in this report.")
            return
        pick = st.selectbox("Select ticker", symbols, key="lynch_detail_pick")
        ticker_data = get_lynch_ticker_by_name(tickers, pick)
        if ticker_data:
            render_lynch_ticker_detail(pick, ticker_data)
        else:
            st.warning(f"No data for {pick}.")


def _fmt_num(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):.2f}"


def _fmt_pct(value) -> str:
    if value is None:
        return "—"
    return f"{float(value):.1f}%"
