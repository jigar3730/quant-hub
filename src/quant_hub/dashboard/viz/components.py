"""Reusable dashboard UI components."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from quant_hub.dashboard.viz.data import (
    LAUNCHPAD_SCORE_LABELS,
    LAUNCHPAD_TECHNICAL_KEYS,
    SCORE_LABELS,
    TECHNICAL_KEYS,
    TIER_COLORS,
    scores_to_dataframe,
)
from quant_hub.dashboard.viz.design_tokens import CHART_PALETTE, COLORS
from quant_hub.dashboard.viz.launchpad_score_guide import (
    LAUNCHPAD_COMPONENT_HELP,
    LAUNCHPAD_COMPONENT_SUMMARY,
)
from quant_hub.dashboard.viz.labels import tier_friendly
from quant_hub.dashboard.viz.navigation import ticker_link_html
from quant_hub.dashboard.viz.ticker_history_components import render_ticker_history_panel
from quant_hub.infrastructure.postgres.repository import ScanRepository
from quant_hub.dashboard.viz.score_guide import COMPONENT_HELP, COMPONENT_SUMMARY
from quant_hub.dashboard.viz.signals import component_action, render_signal_insights_panel
from quant_hub.dashboard.viz.styles import PLOTLY_LAYOUT, TIER_BADGE_CSS
from quant_hub.dashboard.viz.validation import regime_looks_synthetic
from quant_hub.data.news import fetch_ticker_news, fetch_ticker_snapshot
from quant_hub.filters.eligibility import FILTER_LABELS


def apply_chart_style(fig: go.Figure, *, height: int | None = None) -> go.Figure:
    fig.update_layout(**PLOTLY_LAYOUT)
    if height:
        fig.update_layout(height=height)
    return fig


def tier_badge_html(tier: str, *, friendly: bool = True) -> str:
    style = TIER_BADGE_CSS.get(tier, TIER_BADGE_CSS["Tier 3"])
    label = tier_friendly(tier, short=True) if friendly else tier
    return f"<span class='tier-badge' style='{style}' title='{tier}'>{label}</span>"


def render_scan_header(
    report_path: str,
    summary: dict,
    regime: dict,
    *,
    scan_date: str | None = None,
    title: str = "Breakout Scanner",
) -> None:
    tiers = summary["tier_counts"]
    t1 = tiers.get("Tier 1", 0)
    t2 = tiers.get("Tier 2", 0)
    st.markdown(
        f"""
        <div class="scan-header">
            <h1>{title}</h1>
            <p>
              {summary['universe_size']} tickers scanned
              &nbsp;|&nbsp; {summary['eligible_count']} eligible
              &nbsp;|&nbsp; {t1} high conviction
              &nbsp;|&nbsp; {t2} watchlist
              &nbsp;|&nbsp; Regime: <strong>{regime['label'].title()}</strong>
              (×{regime['multiplier']})
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_regime_panel(regime: dict) -> None:
    if regime.get("interval") == "1wk":
        st.markdown('<div class="info-card"><h4>Weekly Swing Context</h4>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        c1.metric("Interval", regime.get("interval", "1wk"))
        c2.metric("History", regime.get("period", "10y"))
        st.markdown(
            "Swing scans use **10-year weekly OHLCV** and finance-vibe EMA/RSI/MACD rules."
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if regime_looks_synthetic(regime):
        st.warning(
            "SPY price looks like **synthetic dry-run data**, not live market data. "
            "Reload the archived scan from the sidebar, or run "
            "`quant-scan --report both` without `--dry-run`."
        )
    st.markdown('<div class="info-card"><h4>Market Regime (SPY)</h4>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    spy = regime.get("spy_price")
    c1.metric("SPY Price", f"${spy}" if spy is not None else "—")
    sma50 = regime.get("sma50")
    c2.metric("SMA 50", f"${sma50}" if sma50 is not None else "—")
    sma200 = regime.get("sma200")
    c3.metric("SMA 200", f"${sma200}" if sma200 is not None else "—")
    ret = regime.get("return_63d_pct")
    c4.metric("63d Return", f"{ret}%" if ret is not None else "—")
    meaning = regime.get("meaning")
    high = regime.get("high_52w")
    below = regime.get("pct_below_52w_high")
    if meaning or high is not None:
        below_s = f"{below}%" if below is not None else "—"
        high_s = f"${high}" if high is not None else "—"
        st.markdown(
            f"**{meaning or 'Market regime'}**  \n"
            f"52-week high: {high_s} ({below_s} below high)"
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_tier_chart(tiers: dict) -> go.Figure:
    labels = ["Tier 1", "Tier 2", "Tier 3", "filtered"]
    values = [tiers.get(label, 0) for label in labels]
    colors = [TIER_COLORS[label] for label in labels]
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.45, marker_colors=colors))
    fig.update_layout(title="Tier Distribution", showlegend=True, height=320)
    return apply_chart_style(fig)


def render_exclusion_chart(breakdown: dict) -> go.Figure | None:
    if not breakdown:
        return None
    labels = [FILTER_LABELS.get(k, k.replace("_", " ").title()) for k in breakdown]
    fig = px.bar(
        x=list(breakdown.values()),
        y=labels,
        orientation="h",
        labels={"x": "Tickers", "y": ""},
        color=list(breakdown.values()),
        color_continuous_scale="Reds",
    )
    fig.update_layout(title="Why Stocks Were Excluded", showlegend=False, coloraxis_showscale=False)
    return apply_chart_style(fig, height=max(220, len(breakdown) * 36))


def render_score_histogram(eligible_df: pd.DataFrame) -> go.Figure:
    fig = px.histogram(
        eligible_df,
        x="final_score",
        nbins=12,
        color_discrete_sequence=[COLORS["primary"]],
        labels={"final_score": "Final Score"},
    )
    fig.update_layout(title="Score Distribution (Eligible)")
    return apply_chart_style(fig, height=280)


def render_heatmap(heat_df: pd.DataFrame) -> go.Figure:
    melt = heat_df.melt(id_vars="ticker", var_name="component", value_name="score")
    fig = px.density_heatmap(
        melt,
        x="component",
        y="ticker",
        z="score",
        histfunc="avg",
        color_continuous_scale="Blues",
        labels={"score": "Points"},
    )
    fig.update_layout(
        title="Component Scores by Ticker",
        height=max(320, len(heat_df) * 24),
    )
    return apply_chart_style(fig)


def render_scatter(scatter_df: pd.DataFrame) -> go.Figure:
    fig = px.scatter(
        scatter_df,
        x="compression",
        y="rs_market",
        text="ticker",
        size="final_score",
        color="tier",
        color_discrete_map=TIER_COLORS,
        hover_data=["final_score", "tier"],
        labels={
            "compression": "Compression Score",
            "rs_market": "RS vs Market Score",
            "final_score": "Final Score",
        },
    )
    fig.update_traces(textposition="top center", marker=dict(line=dict(width=1, color="white")))
    fig.update_layout(title="Compression vs Relative Strength")
    return apply_chart_style(fig, height=400)


def render_score_bars(scores_df: pd.DataFrame, ticker: str, scores: dict | None = None) -> go.Figure:
    custom = []
    if scores is not None and "key" in scores_df.columns:
        for _, row in scores_df.iterrows():
            comp = scores.get(row["key"], {})
            custom.append(
                f"<b>{row['component']}</b><br>{component_action(row['key'], comp)}"
            )
    fig = px.bar(
        scores_df,
        x="score",
        y="component",
        orientation="h",
        range_x=[0, max(scores_df["max"].max(), 1)],
        text=scores_df["score"].round(1),
        color="pct",
        color_continuous_scale="Blues",
        labels={"score": "Score", "component": "", "pct": "% of max"},
    )
    fig.update_traces(textposition="outside")
    if custom:
        fig.update_traces(customdata=custom, hovertemplate="%{customdata}<extra></extra>")
    fig.update_layout(title=f"{ticker} — Component Scores", showlegend=False)
    return apply_chart_style(fig, height=360)


def render_radar(scores_df: pd.DataFrame, ticker: str) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatterpolar(
            r=scores_df["pct"].tolist(),
            theta=scores_df["component"].tolist(),
            fill="toself",
            name=ticker,
            line_color=COLORS["primary"],
            fillcolor="rgba(79,70,229,0.25)",
        )
    )
    fig.update_layout(
        title=f"{ticker} — Score Profile",
        polar=dict(radialaxis=dict(range=[0, 100], tickformat=".0f")),
        height=360,
    )
    return apply_chart_style(fig)


def render_compare_radar(ticker_list: list[dict]) -> go.Figure | None:
    fig = go.Figure()
    palette = CHART_PALETTE
    for i, t in enumerate(ticker_list):
        scores_df = scores_to_dataframe(t)
        if scores_df.empty:
            continue
        fig.add_trace(
            go.Scatterpolar(
                r=scores_df["pct"].tolist(),
                theta=scores_df["component"].tolist(),
                fill="toself",
                name=t["ticker"],
                opacity=0.6,
                line_color=palette[i % len(palette)],
            )
        )
    if not fig.data:
        return None
    fig.update_layout(
        title="Ticker Comparison",
        polar=dict(radialaxis=dict(range=[0, 100])),
        height=420,
    )
    return apply_chart_style(fig)


def render_eligibility_panel(ticker_data: dict) -> None:
    st.markdown("#### Eligibility Checks")
    checks = ticker_data.get("eligibility", {}).get("checks", [])
    if not checks:
        st.info("No eligibility data.")
        return

    for check in checks:
        passed = check.get("passed")
        if passed:
            badge = "<span class='pass-badge'>PASS</span>"
        else:
            badge = "<span class='fail-badge'>FAIL</span>"
        rule = check.get("rule", "").replace("_", " ").title()
        value = check.get("value")
        threshold = check.get("threshold", "")
        detail = check.get("detail")

        with st.container():
            cols = st.columns([1, 4])
            cols[0].markdown(badge, unsafe_allow_html=True)
            body = f"**{rule}** — threshold: {threshold}"
            if isinstance(value, dict):
                parts = [f"{k.replace('_', ' ')}: **{v}**" for k, v in value.items()]
                body += "  \n" + " · ".join(parts)
            elif value is not None:
                body += f"  \nValue: **{value}**"
            if detail and not passed:
                body += f"  \n_{detail}_"
            cols[1].markdown(body)


def _render_score_cards(
    ticker_data: dict,
    keys: tuple[str, ...],
    title: str,
    *,
    score_labels: dict[str, str] | None = None,
    component_help: dict[str, str] | None = None,
    component_summary: dict[str, str] | None = None,
) -> None:
    scores = ticker_data.get("scores") or {}
    labels = score_labels or SCORE_LABELS
    help_map = component_help or COMPONENT_HELP
    summary_map = component_summary or COMPONENT_SUMMARY
    subset = [(k, labels[k]) for k in keys if k in labels]
    if not subset:
        return

    st.markdown(f"#### {title}")
    for key, label in subset:
        comp = scores.get(key)
        if not comp:
            continue
        score = float(comp.get("score", 0))
        max_pts = comp.get("max", 0)
        pct = (score / max_pts * 100) if max_pts else 0
        help_text = help_map.get(key, "")
        summary_text = summary_map.get(key, "")
        st.markdown(
            f"""
            <div class="component-card">
              <strong>{label}</strong>
              <span style="float:right">{score:.1f} / {max_pts}</span>
              <div style="background:{COLORS['border']};border-radius:4px;height:6px;margin:6px 0;">
                <div style="background:{COLORS['primary']};width:{pct:.0f}%;
                     height:6px;border-radius:4px;"></div>
              </div>
              <small style="color:{COLORS['text_secondary']}">{comp.get('meaning', '') or summary_text}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if help_text:
            st.caption(f"What to look for: {help_text}")
        raw = comp.get("raw", {})
        if raw:
            with st.expander(f"Raw data — {label}"):
                st.json(raw)


def render_component_cards(ticker_data: dict, *, strategy_id: str = "breakout") -> None:
    scores = ticker_data.get("scores") or {}
    if not scores:
        st.warning("No scoring data — stock did not pass eligibility filters.")
        return
    if strategy_id == "launchpad":
        _render_score_cards(
            ticker_data,
            LAUNCHPAD_TECHNICAL_KEYS,
            "Scoring Components",
            score_labels=LAUNCHPAD_SCORE_LABELS,
            component_help=LAUNCHPAD_COMPONENT_HELP,
            component_summary=LAUNCHPAD_COMPONENT_SUMMARY,
        )
        return
    _render_score_cards(ticker_data, tuple(SCORE_LABELS.keys()), "Scoring Components")


@st.cache_data(ttl=600, show_spinner=False)
def _load_ticker_news(ticker: str, count: int) -> list[dict]:
    return fetch_ticker_news(ticker, count=count)


@st.cache_data(ttl=300, show_spinner=False)
def _load_ticker_snapshot(ticker: str) -> dict | None:
    return fetch_ticker_snapshot(ticker)


def _format_market_cap(value: float | None) -> str:
    if not value:
        return "—"
    if value >= 1e12:
        return f"${value / 1e12:.2f}T"
    if value >= 1e9:
        return f"${value / 1e9:.1f}B"
    if value >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value:,.0f}"


def render_ticker_news_panel(
    ticker: str,
    *,
    compact: bool = False,
    scan_date: str | None = None,
) -> None:
    st.markdown("#### Live market data")
    if scan_date:
        st.markdown(
            f'<div class="live-data-label">Yahoo Finance — may differ from scan on {scan_date}</div>',
            unsafe_allow_html=True,
        )

    snapshot = _load_ticker_snapshot(ticker)
    if snapshot:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Live Price", f"${snapshot['price']:,.2f}")
        change = snapshot.get("change_pct")
        c2.metric("Day Change", f"{change:+.2f}%" if change is not None else "—")
        c3.metric("Market Cap", _format_market_cap(snapshot.get("market_cap")))
        year_chg = snapshot.get("year_change_pct")
        c4.metric("1Y Change", f"{year_chg:+.1f}%" if year_chg is not None else "—")
        day_hi = snapshot.get("day_high")
        day_lo = snapshot.get("day_low")
        if day_hi and day_lo:
            currency = snapshot.get("currency", "USD")
            st.caption(f"Today's range: ${day_lo:,.2f} – ${day_hi:,.2f} ({currency})")
    else:
        st.caption("Live market data unavailable — scores below reflect the scan date.")

    st.markdown("#### Latest news")
    news = _load_ticker_news(ticker, count=3 if compact else 8)
    if not news:
        st.info("No recent news found for this ticker.")
        return

    for i, article in enumerate(news):
        title = article["title"]
        url = article.get("url")
        meta_parts = [article.get("publisher"), article.get("published")]
        meta = " · ".join(part for part in meta_parts if part)

        if url:
            st.markdown(f"**[{title}]({url})**")
        else:
            st.markdown(f"**{title}**")
        if meta:
            st.caption(meta)
        summary = article.get("summary", "")
        if summary:
            st.markdown(summary)
        if i < len(news) - 1:
            st.markdown("---")


def render_score_history(history: list[dict], ticker: str) -> go.Figure | None:
    if not history:
        return None
    df = pd.DataFrame(history).sort_values("scan_date")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["scan_date"],
            y=df["final_score"],
            mode="lines+markers",
            name="Final score",
            line=dict(color=COLORS["primary"], width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["scan_date"],
            y=df["normalized_score"],
            mode="lines+markers",
            name="Normalized",
            line=dict(color=COLORS["text_muted"], width=1, dash="dot"),
        )
    )
    fig.update_layout(
        title=f"{ticker} — Score History",
        xaxis_title="Scan date",
        yaxis_title="Score",
        yaxis=dict(range=[0, 100]),
        height=320,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return apply_chart_style(fig)


def render_technical_panel(ticker_data: dict, ticker: str, *, strategy_id: str = "breakout") -> None:
    scores = ticker_data.get("scores") or {}
    technical_keys = LAUNCHPAD_TECHNICAL_KEYS if strategy_id == "launchpad" else TECHNICAL_KEYS
    if not any(scores.get(k) for k in technical_keys):
        st.info("Technical scores unavailable — ticker did not pass eligibility filters.")
        return

    technical_df = scores_to_dataframe(ticker_data, strategy_id=strategy_id)
    technical_df = technical_df[technical_df["key"].isin(technical_keys)]
    if not technical_df.empty:
        st.plotly_chart(
            render_score_bars(technical_df, ticker, scores=ticker_data.get("scores") or {}),
            use_container_width=True,
        )
        st.plotly_chart(render_radar(technical_df, ticker), use_container_width=True)
    if strategy_id == "launchpad":
        _render_score_cards(
            ticker_data,
            LAUNCHPAD_TECHNICAL_KEYS,
            "Technical Scores",
            score_labels=LAUNCHPAD_SCORE_LABELS,
            component_help=LAUNCHPAD_COMPONENT_HELP,
            component_summary=LAUNCHPAD_COMPONENT_SUMMARY,
        )
    else:
        _render_score_cards(ticker_data, TECHNICAL_KEYS, "Technical Scores")


def render_ticker_detail(
    ticker: str,
    ticker_data: dict,
    *,
    compact_news: bool = False,
    show_history: bool = True,
    scan_date: str | None = None,
    repo: ScanRepository | None = None,
    strategy_id: str = "breakout",
) -> None:
    """Unified detail: news, technical scores, eligibility, history."""
    tier = ticker_data.get("tier", "filtered")
    st.markdown(
        f"## {ticker_link_html(ticker)} {tier_badge_html(tier)}",
        unsafe_allow_html=True,
    )
    if scan_date:
        st.markdown(
            f'<div class="scan-as-of">Scores and eligibility as of scan date <strong>{scan_date}</strong></div>',
            unsafe_allow_html=True,
        )
    st.info(ticker_data.get("tier_reason", ""))

    summary = ticker_data.get("summary", {})
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Final Score", f"{summary.get('final_adjusted_score', 0):.1f}")
    m2.metric("Universe Rank", f"{summary.get('normalized_score', 0):.1f}")
    m3.metric("Raw Score", f"{summary.get('raw_score', 0):.1f}")
    m4.metric("Sector ETF", ticker_data.get("sector_etf") or "—")

    if ticker_data.get("scores"):
        render_signal_insights_panel(ticker_data)

    render_ticker_news_panel(ticker, compact=compact_news, scan_date=scan_date)

    tab_tech, tab_elig = st.tabs(["Technical", "Eligibility"])
    with tab_tech:
        render_technical_panel(ticker_data, ticker, strategy_id=strategy_id)
    with tab_elig:
        render_eligibility_panel(ticker_data)

    if show_history and repo is not None:
        st.divider()
        render_ticker_history_panel(repo, ticker, key_prefix="breakout_detail", show_header=True)


def build_leaderboard_df(df: pd.DataFrame) -> pd.DataFrame:
    display = df.sort_values("final_score", ascending=False).copy()
    display["score"] = display["final_score"].round(1)
    display["norm"] = display["normalized_score"].round(1)
    return display[
        ["ticker", "tier", "score", "norm", "sector_etf", "tier_reason"]
    ]


def get_ticker_by_name(tickers: list[dict], name: str) -> dict | None:
    return next((t for t in tickers if t["ticker"] == name), None)


def filter_reason_label(code: str | None) -> str:
    if not code:
        return ""
    return FILTER_LABELS.get(code, code.replace("_", " ").title())


__all__ = [
    "build_leaderboard_df",
    "get_ticker_by_name",
    "render_compare_radar",
    "render_component_cards",
    "render_eligibility_panel",
    "render_exclusion_chart",
    "render_heatmap",
    "render_radar",
    "render_regime_panel",
    "render_scan_header",
    "render_scatter",
    "render_score_bars",
    "render_score_history",
    "render_score_histogram",
    "render_technical_panel",
    "render_ticker_detail",
    "render_ticker_news_panel",
    "render_tier_chart",
    "tier_badge_html",
]
