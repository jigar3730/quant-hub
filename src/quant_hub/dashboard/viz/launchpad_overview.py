"""Launchpad Overview renderers — data-dense scan briefing."""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from quant_hub.dashboard.viz.components import apply_chart_style, render_regime_panel
from quant_hub.dashboard.viz.design_tokens import COLORS
from quant_hub.dashboard.viz.labels import tier_friendly
from quant_hub.dashboard.viz.launchpad_insights import (
    SCORE_FACTORS,
    build_launchpad_overview_vm,
    load_prior_report,
)
from quant_hub.dashboard.viz.navigation import set_detail_ticker
from quant_hub.dashboard.viz.styles import PLOTLY_CONFIG
from quant_hub.dashboard.viz.table_helpers import (
    merge_column_config,
    table_column_order,
    with_ticker_links,
)
from quant_hub.infrastructure.postgres.repository import ScanRepository

FACTOR_COLORS = {
    "squeeze_intensity": COLORS["primary"],
    "volume_vacuum_depth": COLORS["accent_violet"],
    "tightness_percentile": COLORS["warning_solid"],
    "trend_proximity_match": COLORS["success_solid"],
}

GRID_COLUMNS = [
    "ticker",
    "status",
    "tier",
    "final_score",
    "normalized_score",
    "score_delta",
    "squeeze_pts",
    "tightness_pts",
    "volume_pts",
    "trend_pts",
    "macd_ignition",
    "macd_phase",
    "squeeze_ratio",
    "tightness_rank_pct",
    "rvol",
    "ema50_distance_pct",
    "sector_etf",
    "reason",
]

COIL_COLUMNS = [
    "ticker",
    "status",
    "squeeze_ratio",
    "tightness_rank_pct",
    "squeeze_pts",
    "tightness_pts",
    "rvol",
    "final_score",
    "macd_ignition",
    "macd_phase",
    "sector_etf",
    "reason",
]


def _pct(value: float) -> str:
    return f"{value:.0%}"


def _render_takeaway(takeaway: dict) -> None:
    st.markdown(
        f'<div class="takeaway-card" style="background:{COLORS["primary_soft"]};'
        f'border:1px solid {COLORS["primary_border"]}">'
        f'<strong>Today\'s takeaway</strong><br>{takeaway["headline"]}</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    prior = takeaway.get("prior_date")
    c1.metric("New actionable", takeaway["new_count"], help=f"Vs prior scan {prior}" if prior else "No prior scan")
    c2.metric("Dropped", takeaway["dropped_count"], help="Left the actionable book vs the prior scan")
    c3.metric("Upgrades", takeaway["upgrade_count"], help="Tier rank improved vs the prior scan")
    c4.metric(
        "Blocked ≥65",
        takeaway["blocked_count"],
        help="Ineligible names that still scored at or above the watchlist bar.",
    )


def _factor_mix_figure(mix: list[dict]) -> go.Figure:
    ordered = list(reversed(mix))
    fig = go.Figure(
        go.Bar(
            x=[row["mean_points"] for row in ordered],
            y=[row["label"] for row in ordered],
            orientation="h",
            marker_color=[FACTOR_COLORS.get(row["key"], COLORS["primary"]) for row in ordered],
            text=[
                f"{row['mean_points']:.1f} / {row['max_points']:.0f}"
                for row in ordered
            ],
            textposition="outside",
            hovertemplate="%{y}<br>Mean %{x:.1f} pts<extra></extra>",
        )
    )
    fig.update_layout(
        title="Mean factor points (actionable)",
        xaxis_title="Points",
        xaxis=dict(range=[0, 45]),
        height=260,
        margin=dict(l=8, r=48, t=44, b=8),
        showlegend=False,
    )
    return apply_chart_style(fig)


def _contributions_figure(rows: list[dict]) -> go.Figure | None:
    if not rows:
        return None
    ordered = list(reversed(rows))
    fig = go.Figure()
    for key, label, _max in SCORE_FACTORS:
        fig.add_trace(
            go.Bar(
                name=label,
                x=[row["parts"].get(key, 0) for row in ordered],
                y=[row["ticker"] for row in ordered],
                orientation="h",
                marker_color=FACTOR_COLORS.get(key, COLORS["primary"]),
                hovertemplate=f"{label}: %{{x:.1f}}<extra></extra>",
            )
        )
    fig.update_layout(
        title="Top actionable — score composition",
        barmode="stack",
        height=max(260, 36 * len(ordered) + 80),
        margin=dict(l=8, r=8, t=44, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis_title="Points",
    )
    return apply_chart_style(fig)


def _render_drivers(drivers: dict) -> None:
    st.markdown("#### Today's factor mix")
    if not drivers["cohort_size"]:
        st.caption("No actionable names — factor mix is empty. See Blocked setups for high scores that failed a gate.")
        return
    mix = drivers["factor_mix"]
    st.plotly_chart(_factor_mix_figure(mix), use_container_width=True, config=PLOTLY_CONFIG)
    st.caption(
        f"MACD ignition: {drivers['macd_ignition_count']} / {drivers['cohort_size']} actionable "
        "(Tier 1 gate, not part of the 100-pt score)."
    )
    zeros = [row for row in mix if row["names_at_zero"]]
    if zeros:
        bits = ", ".join(f"{row['label']} 0 on {row['names_at_zero']}" for row in zeros)
        st.caption(f"Factor completeness: {bits}.")
    contrib_fig = _contributions_figure(drivers["top_contributions"])
    if contrib_fig:
        st.plotly_chart(contrib_fig, use_container_width=True, config=PLOTLY_CONFIG)


def _funnel_figure(stages: list[dict]) -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=[stage["remaining"] for stage in stages],
            y=[stage["label"] for stage in stages],
            orientation="h",
            marker_color=COLORS["primary"],
            text=[stage["remaining"] for stage in stages],
            textposition="outside",
            hovertemplate="%{y}: %{x} remaining<extra></extra>",
        )
    )
    fig.update_layout(
        title="Universe remaining by stage",
        height=280,
        margin=dict(l=8, r=40, t=44, b=8),
        showlegend=False,
        yaxis=dict(autorange="reversed"),
    )
    return apply_chart_style(fig)


def _render_funnel(funnel: dict) -> None:
    st.markdown("#### Universe funnel")
    stages = funnel["stages"]
    st.plotly_chart(_funnel_figure(stages), use_container_width=True, config=PLOTLY_CONFIG)

    rows = []
    for stage in stages:
        reason_text = ", ".join(
            f"{label} {count}" for _code, label, count in stage["reasons"][:3]
        )
        rows.append(
            {
                "Stage": stage["label"],
                "Remaining": stage["remaining"],
                "Dropped": stage["dropped"],
                "Drop %": _pct(stage["drop_pct"]) if stage["id"] != "universe" else "—",
                "Primary reasons": reason_text or "—",
            }
        )
    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Stage": st.column_config.TextColumn("Stage", width="medium"),
            "Primary reasons": st.column_config.TextColumn("Primary reasons", width="large"),
        },
    )


def _delta_frame(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    display = []
    for row in rows:
        display.append(
            {
                "ticker": row["ticker"],
                "From": tier_friendly(row["from_tier"] or "", short=True) if row["from_tier"] else "—",
                "To": tier_friendly(row["to_tier"] or "", short=True) if row["to_tier"] else "—",
                "Δ Score": row["score_delta"],
                "Sector": row.get("sector_etf") or "—",
                "Reason": row.get("drop_reason") or "",
            }
        )
    return pd.DataFrame(display)


def _render_delta_table(df: pd.DataFrame, empty_msg: str, *, key: str) -> None:
    if df.empty:
        st.caption(empty_msg)
        return
    linked = with_ticker_links(df)
    base_cols = [column for column in linked.columns if column != "ticker_link"]
    selection = st.dataframe(
        linked,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
        column_config=merge_column_config(
            {
                "Δ Score": st.column_config.NumberColumn("Δ Score", format="%+.1f"),
            }
        ),
        column_order=table_column_order(base_cols),
    )
    if selection.selection.rows:
        picked = df.iloc[selection.selection.rows[0]]["ticker"]
        set_detail_ticker(picked)


def _render_delta(delta: dict) -> None:
    st.markdown("#### Scan delta")
    if not delta.get("prior_date"):
        st.caption("First scan for this universe — no prior date to compare.")
        return
    st.caption(f"Compared with {delta['prior_date']}.")
    new_df = _delta_frame(delta["new_actionable"])
    dropped_df = _delta_frame(delta["dropped_actionable"])
    up_df = _delta_frame(delta["upgraded"])
    down_df = _delta_frame(delta["downgraded"])
    tab_new, tab_dropped, tab_up, tab_down = st.tabs(
        [
            f"New ({len(new_df)})",
            f"Dropped ({len(dropped_df)})",
            f"Upgraded ({len(up_df)})",
            f"Downgraded ({len(down_df)})",
        ]
    )
    with tab_new:
        _render_delta_table(new_df, "No new actionable names.", key="overview_delta_new")
    with tab_dropped:
        _render_delta_table(dropped_df, "Nothing dropped out.", key="overview_delta_dropped")
    with tab_up:
        _render_delta_table(up_df, "No tier upgrades.", key="overview_delta_up")
    with tab_down:
        _render_delta_table(down_df, "No tier downgrades.", key="overview_delta_down")


def _sector_figure(matrix: dict) -> go.Figure | None:
    sectors = matrix.get("sectors") or []
    tiers = matrix.get("tiers") or []
    if not sectors:
        return None
    lookup = {(cell["sector_etf"], cell["tier"]): cell["count"] for cell in matrix["cells"]}
    z = [[lookup.get((sector, tier), 0) for sector in sectors] for tier in tiers]
    text = [[str(value) if value else "—" for value in row] for row in z]
    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=sectors,
            y=[tier_friendly(tier, short=True) for tier in tiers],
            text=text,
            texttemplate="%{text}",
            colorscale=[[0, COLORS["bg_elevated"]], [1, COLORS["primary"]]],
            showscale=False,
            hovertemplate="%{y} · %{x}: %{z}<extra></extra>",
            xgap=3,
            ygap=3,
        )
    )
    fig.update_layout(
        title="Sector ETF × tier",
        height=220,
        margin=dict(l=8, r=8, t=44, b=8),
    )
    return apply_chart_style(fig)


def _render_sector(matrix: dict) -> None:
    st.markdown("#### Sector concentration")
    fig = _sector_figure(matrix)
    if fig is None:
        st.caption("No sector data on this scan.")
        return
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    sector = matrix.get("dominant_sector")
    share = matrix.get("dominant_actionable_share") or 0.0
    if sector and sector != "—":
        line = f"{sector} is {_pct(share)} of actionable names."
        if matrix.get("concentration_warning"):
            st.warning(line)
        else:
            st.caption(line)


def _grid_column_config() -> dict:
    return merge_column_config(
        {
            "status": st.column_config.TextColumn("Status", width="small"),
            "tier": st.column_config.TextColumn("Tier", width="small"),
            "final_score": st.column_config.ProgressColumn(
                "Final", format="%.1f", min_value=0, max_value=100
            ),
            "normalized_score": st.column_config.NumberColumn("Norm", format="%.1f"),
            "score_delta": st.column_config.NumberColumn("Δ Score", format="%+.1f"),
            "squeeze_pts": st.column_config.ProgressColumn(
                "Squeeze", format="%.0f", min_value=0, max_value=40
            ),
            "tightness_pts": st.column_config.ProgressColumn(
                "Tightness", format="%.0f", min_value=0, max_value=15
            ),
            "volume_pts": st.column_config.ProgressColumn(
                "Volume", format="%.0f", min_value=0, max_value=30
            ),
            "trend_pts": st.column_config.ProgressColumn(
                "Trend", format="%.0f", min_value=0, max_value=15
            ),
            "macd_ignition": st.column_config.CheckboxColumn("MACD on", disabled=True),
            "macd_phase": st.column_config.TextColumn("MACD phase", width="medium"),
            "squeeze_ratio": st.column_config.NumberColumn(
                "Squeeze ratio", format="%.2f", help="BB width / KC width. Lower is tighter."
            ),
            "tightness_rank_pct": st.column_config.NumberColumn(
                "Tightness %ile", format="%.0%", help="Lower means tighter recent candles."
            ),
            "rvol": st.column_config.NumberColumn("RVOL", format="%.2f"),
            "ema50_distance_pct": st.column_config.NumberColumn("Dist EMA50", format="%.1%"),
            "sector_etf": st.column_config.TextColumn("Sector"),
            "reason": st.column_config.TextColumn("Reason", width="large"),
        }
    )


def _render_grid_table(rows: list[dict], *, columns: list[str], key: str, empty: str) -> None:
    if not rows:
        st.caption(empty)
        return
    df = pd.DataFrame(rows)
    keep = [column for column in columns if column in df.columns]
    shown = with_ticker_links(df[keep].copy())
    if "tier" in shown.columns:
        shown["tier"] = shown["tier"].map(lambda value: tier_friendly(str(value), short=True))
    selection = st.dataframe(
        shown,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=key,
        column_config=_grid_column_config(),
        column_order=table_column_order(keep),
    )
    st.download_button(
        "Download CSV",
        df[keep].to_csv(index=False).encode(),
        file_name=f"launchpad_overview_{key}.csv",
        mime="text/csv",
        key=f"{key}_download",
    )
    if selection.selection.rows:
        picked = df.iloc[selection.selection.rows[0]]["ticker"]
        set_detail_ticker(picked)


def _render_score_grid(grid: dict) -> None:
    st.markdown("#### Score grid")
    st.caption(
        "Actionable book, eligible near-misses, and high-score names that failed a hard gate. "
        "Tightest coils ranks the same set by raw squeeze ratio, then candle tightness."
    )
    actionable = grid["actionable"]
    near = grid["near_miss"]
    blocked = grid["blocked"]
    coils = grid["coils"]
    tab_a, tab_n, tab_b, tab_c = st.tabs(
        [
            f"Actionable ({len(actionable)})",
            f"Near miss ({len(near)})",
            f"Blocked setups ({len(blocked)})",
            f"Tightest coils ({len(coils)})",
        ]
    )
    with tab_a:
        _render_grid_table(
            actionable,
            columns=GRID_COLUMNS,
            key="overview_grid_actionable",
            empty="No Tier 1 or Tier 2 names in this scan.",
        )
    with tab_n:
        _render_grid_table(
            near,
            columns=GRID_COLUMNS,
            key="overview_grid_near",
            empty="No eligible names sitting just below a tier gate.",
        )
    with tab_b:
        _render_grid_table(
            blocked,
            columns=GRID_COLUMNS,
            key="overview_grid_blocked",
            empty="No ineligible names scored at or above 65.",
        )
    with tab_c:
        _render_grid_table(
            coils,
            columns=COIL_COLUMNS,
            key="overview_grid_coils",
            empty="No coil metrics on the decision set.",
        )


def render_launchpad_overview(
    *,
    summary: dict,
    regime: dict,
    tickers: list[dict],
    repo: ScanRepository | None = None,
    strategy_id: str = "launchpad",
    universe_id: str | None = None,
    scan_date: date | str | None = None,
) -> None:
    render_regime_panel(regime)
    prior = load_prior_report(
        repo,
        strategy_id=strategy_id,
        universe_id=universe_id,
        scan_date=scan_date,
    )
    report = {
        "strategy_id": strategy_id,
        "universe_id": universe_id,
        "scan_date": str(scan_date) if scan_date is not None else "",
        "scan_summary": summary,
        "market_regime": regime,
        "tickers": tickers,
    }
    vm = build_launchpad_overview_vm(report, prior)

    _render_takeaway(vm["takeaway"])
    left, right = st.columns(2)
    with left:
        _render_drivers(vm["drivers"])
    with right:
        _render_funnel(vm["funnel"])
    d_left, d_right = st.columns(2)
    with d_left:
        _render_delta(vm["delta"])
    with d_right:
        _render_sector(vm["sector"])
    _render_score_grid(vm["grid"])
