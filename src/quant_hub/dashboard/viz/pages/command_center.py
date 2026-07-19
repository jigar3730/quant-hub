"""Daily Command Center — Launchpad + Lynch briefing page."""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_hub.dashboard.viz.components import apply_chart_style
from quant_hub.dashboard.viz.design_tokens import COLORS
from quant_hub.dashboard.viz.labels import STRATEGY_DISPLAY, tier_friendly
from quant_hub.dashboard.viz.navigation import set_detail_ticker
from quant_hub.dashboard.viz.styles import PLOTLY_CONFIG
from quant_hub.dashboard.viz.table_helpers import (
    merge_column_config,
    table_column_order,
    with_yahoo_ticker_links,
)
from quant_hub.dashboard.viz.ticker_history_components import render_ticker_history_panel
from quant_hub.digest.command_center import (
    COMMAND_CENTER_STRATEGIES,
    build_command_center_payload,
)
from quant_hub.infrastructure.postgres.repository import ScanRepository


def _universe_label(universe_id: str) -> str:
    return universe_id.replace("_", " ").upper()


def _render_header(payload: dict, scan_date: date) -> None:
    per = payload["per_strategy"]
    total_actionable = sum(v["actionable"] for v in per.values())
    regime = (payload.get("regime_label") or "unknown").title()
    st.markdown(
        f"""
        <div class="scan-header">
            <h1>Daily Command Center</h1>
            <p>
              {scan_date} &nbsp;|&nbsp; {payload['run_count']} scan runs
              &nbsp;|&nbsp; {total_actionable} actionable signals
              &nbsp;|&nbsp; {payload['overlap_count']} Launchpad+Lynch overlaps
              &nbsp;|&nbsp; Regime: <strong>{regime}</strong>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_summary_metrics(payload: dict) -> None:
    per = payload["per_strategy"]
    cols = st.columns(len(COMMAND_CENTER_STRATEGIES) + 1)
    for col, strategy_id in zip(cols, COMMAND_CENTER_STRATEGIES, strict=False):
        stats = per.get(strategy_id, {})
        label = STRATEGY_DISPLAY.get(strategy_id, strategy_id.title())
        col.metric(
            label,
            stats.get("actionable", 0),
            help=(
                f"{stats.get('universes', 0)} universe(s) scanned · "
                f"{stats.get('tier1', 0)} top-tier"
            ),
        )
    cols[-1].metric(
        "Overlap",
        payload["overlap_count"],
        help="Tickers actionable in both Launchpad and Lynch today.",
    )


def _render_coverage_heatmap(payload: dict) -> None:
    coverage = payload.get("coverage") or []
    if not coverage:
        st.info("No scan runs recorded for this date.")
        return

    universes = sorted({c["universe_id"] for c in coverage})
    strategies = [s for s in COMMAND_CENTER_STRATEGIES if any(c["strategy_id"] == s for c in coverage)]
    if not strategies:
        st.info("No recognized strategy runs for this date.")
        return

    lookup = {(c["strategy_id"], c["universe_id"]): c["actionable_count"] for c in coverage}
    z: list[list[float | None]] = []
    text: list[list[str]] = []
    for strategy_id in strategies:
        row_z: list[float | None] = []
        row_text: list[str] = []
        for universe_id in universes:
            if (strategy_id, universe_id) in lookup:
                count = lookup[(strategy_id, universe_id)]
                row_z.append(count)
                row_text.append(str(count))
            else:
                row_z.append(None)
                row_text.append("—")
        z.append(row_z)
        text.append(row_text)

    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=[_universe_label(u) for u in universes],
            y=[STRATEGY_DISPLAY.get(s, s.title()) for s in strategies],
            text=text,
            texttemplate="%{text}",
            colorscale=[[0, COLORS["bg_elevated"]], [1, COLORS["primary"]]],
            showscale=True,
            hovertemplate="%{y} · %{x}<br>Actionable: %{text}<extra></extra>",
            xgap=3,
            ygap=3,
        )
    )
    fig.update_layout(
        title="Actionable signals by scanner and universe (blank = not scanned)",
        height=90 + len(strategies) * 60,
    )
    st.plotly_chart(apply_chart_style(fig), use_container_width=True, config=PLOTLY_CONFIG)


def _render_overlap(payload: dict, *, scan_date: date) -> None:
    overlap = payload.get("launchpad_lynch_overlap") or []
    st.markdown("### Launchpad + Lynch overlap")
    if not overlap:
        st.caption("No tickers were actionable in both Launchpad and Lynch today.")
        return

    rows = []
    for item in overlap:
        launchpad = item.get("launchpad") or {}
        lynch = item.get("lynch") or {}
        rows.append(
            {
                "ticker": item["ticker"],
                "Launchpad tier": tier_friendly(launchpad.get("tier") or "", short=True),
                "Launchpad score": (
                    round(launchpad["final_score"], 1)
                    if launchpad.get("final_score") is not None
                    else None
                ),
                "Lynch tier": tier_friendly(lynch.get("tier") or "", short=True),
                "Lynch score": (
                    round(lynch["final_score"], 1)
                    if lynch.get("final_score") is not None
                    else None
                ),
                "Universes": ", ".join(
                    sorted(
                        {
                            u
                            for u in (
                                launchpad.get("universe_id"),
                                lynch.get("universe_id"),
                            )
                            if u
                        }
                    )
                )
                or "—",
            }
        )
    df = with_yahoo_ticker_links(pd.DataFrame(rows))
    base_cols = [c for c in df.columns if c != "ticker_link"]
    selection = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="command_center_overlap_select",
        column_config=merge_column_config({
            "Launchpad score": st.column_config.NumberColumn("Launchpad score", format="%.1f"),
            "Lynch score": st.column_config.NumberColumn("Lynch score", format="%.1f"),
        }),
        column_order=table_column_order(base_cols),
    )
    st.download_button(
        "Download overlap CSV",
        pd.DataFrame(rows).to_csv(index=False).encode(),
        file_name=f"command_center_overlap_{scan_date}.csv",
        mime="text/csv",
    )
    if selection.selection.rows:
        picked = rows[selection.selection.rows[0]]["ticker"]
        set_detail_ticker(picked)


def _delta_frame(deltas: list[dict], field: str) -> pd.DataFrame:
    rows = []
    for d in deltas:
        values = d.get(field) or []
        for value in values:
            ticker = value["ticker"] if isinstance(value, dict) else value
            extra = value.get("appearances") if isinstance(value, dict) else None
            rows.append(
                {
                    "ticker": ticker,
                    "Scanner": d["strategy_label"],
                    "Universe": _universe_label(d["universe_id"]),
                    "Appearances": extra,
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty and df["Appearances"].isna().all():
        df = df.drop(columns=["Appearances"])
    return df


def _render_deltas(payload: dict) -> None:
    deltas = payload.get("deltas") or []
    st.markdown("### Signal changes vs prior scan")
    if not deltas:
        st.caption("No comparable prior scans found.")
        return

    new_df = _delta_frame(deltas, "new_entrants")
    dropped_df = _delta_frame(deltas, "dropped")
    persistent_df = _delta_frame(deltas, "persistent")

    tab_new, tab_dropped, tab_persist = st.tabs(
        [
            f"New today ({len(new_df)})",
            f"Dropped ({len(dropped_df)})",
            f"Persistent ({len(persistent_df)})",
        ]
    )
    with tab_new:
        _render_delta_table(new_df, "No new actionable names vs the prior scan.")
    with tab_dropped:
        _render_delta_table(dropped_df, "Nothing dropped out vs the prior scan.")
    with tab_persist:
        _render_delta_table(
            persistent_df,
            "No names have persisted across the recent scan window yet.",
        )


def _render_delta_table(df: pd.DataFrame, empty_msg: str) -> None:
    if df.empty:
        st.caption(empty_msg)
        return
    linked = with_yahoo_ticker_links(df)
    base_cols = [c for c in linked.columns if c != "ticker_link"]
    st.dataframe(
        linked,
        use_container_width=True,
        hide_index=True,
        column_config=merge_column_config({}),
        column_order=table_column_order(base_cols),
    )


def _render_ticker_360(repo: ScanRepository, payload: dict, detail_ticker: str | None) -> None:
    st.markdown("### Ticker 360")
    overlap_symbols = [c["ticker"] for c in payload.get("launchpad_lynch_overlap") or []]
    default_index = 0
    options = overlap_symbols or []
    if detail_ticker and detail_ticker in options:
        default_index = options.index(detail_ticker)
    elif detail_ticker:
        options = [detail_ticker, *options]

    if not options:
        st.caption("Select an overlap ticker above, or use the sidebar lookup, to see its full history.")
        return

    active = st.selectbox(
        "Ticker",
        options=options,
        index=default_index,
        key="command_center_ticker_360",
    )
    if active:
        set_detail_ticker(active)
        render_ticker_history_panel(repo, active, key_prefix="command_center", show_header=False)


def render_command_center(
    repo: ScanRepository,
    *,
    scan_date: date,
    detail_ticker: str | None = None,
) -> None:
    payload = build_command_center_payload(repo, scan_date=scan_date)

    _render_header(payload, scan_date)
    _render_summary_metrics(payload)
    st.divider()
    _render_coverage_heatmap(payload)
    st.divider()
    _render_overlap(payload, scan_date=scan_date)
    st.divider()
    _render_deltas(payload)
    st.divider()
    _render_ticker_360(repo, payload, detail_ticker)
