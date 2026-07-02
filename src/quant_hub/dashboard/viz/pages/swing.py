"""Swing dashboard tab renderers."""

from __future__ import annotations

import streamlit as st

from quant_hub.dashboard.viz.components import render_eligibility_panel
from quant_hub.dashboard.viz.labels import tier_friendly
from quant_hub.dashboard.viz.navigation import set_detail_ticker, ticker_link_html
from quant_hub.dashboard.viz.styles import PLOTLY_CONFIG
from quant_hub.dashboard.viz.swing_filters import (
    SwingFilters,
    apply_swing_filters,
    swing_setups_dataframe,
    swing_universe_dataframe,
)
from quant_hub.dashboard.viz.swing_score_guide import render_swing_score_guide
from quant_hub.dashboard.viz.table_helpers import (
    merge_column_config,
    table_column_order,
    with_yahoo_ticker_links,
)
from quant_hub.dashboard.viz.ux_helpers import render_swing_takeaway
from quant_hub.infrastructure.postgres.repository import ScanRepository
from quant_hub.strategies.swing.scanner import SWING_FILTER_LABELS


def get_swing_ticker_by_name(tickers: list[dict], symbol: str) -> dict | None:
    symbol = symbol.upper()
    return next((t for t in tickers if t.get("ticker", "").upper() == symbol), None)


def render_swing_header(
    summary: dict,
    regime: dict,
    report_label: str,
    *,
    scan_date=None,
) -> None:
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
    st.caption(f"Report: {report_label}")


def _swing_table_columns(*, setups_only: bool = False) -> dict:
    return merge_column_config({
        "status": st.column_config.TextColumn("Status"),
        "setup_type": st.column_config.TextColumn("Setup"),
        "score": st.column_config.ProgressColumn(
            "Score",
            format="%.0f",
            min_value=0,
            max_value=100,
            help="Quality score: partial rule credit minus penalties (0–100).",
        ),
        "quality": st.column_config.TextColumn(
            "Grade",
            help="A/B/C/D quality band from fine-grained rubric.",
        ),
        "close": st.column_config.NumberColumn("Close", format="%.2f"),
        "rsi": st.column_config.NumberColumn("RSI", format="%.1f"),
        "ema20": st.column_config.NumberColumn("EMA20", format="%.2f"),
        "ema50": st.column_config.NumberColumn("EMA50", format="%.2f"),
        "atr": st.column_config.NumberColumn("ATR", format="%.2f"),
        "macd_hist": st.column_config.NumberColumn("MACD hist", format="%.4f"),
        "checks": st.column_config.TextColumn(
            "Rules passed",
            help="Setup rules passed out of 5 on the scored side.",
        ),
        "reason": st.column_config.TextColumn("Notes / rejection", width="large"),
        "notes": st.column_config.TextColumn("Notes", width="medium"),
    })


def _swing_display_columns(df, *, setups_only: bool = False) -> list[str]:
    if setups_only:
        preferred = [
            "ticker",
            "setup_type",
            "score",
            "quality",
            "close",
            "rsi",
            "checks",
            "ema20",
            "ema50",
            "atr",
            "macd_hist",
            "notes",
        ]
    else:
        preferred = [
            "ticker",
            "status",
            "setup_type",
            "score",
            "quality",
            "close",
            "rsi",
            "checks",
            "ema20",
            "ema50",
            "atr",
            "macd_hist",
            "reason",
        ]
    return [column for column in preferred if column in df.columns]


def render_swing_ticker_detail(ticker: str, data: dict) -> None:
    detail = data.get("setup_detail") or {}
    tier = data.get("tier", "filtered")
    summary = data.get("summary") or {}
    swing_score = detail.get("swing_score", summary.get("swing_score"))
    base_score = detail.get("base_score")
    penalty_total = detail.get("penalty_total")
    quality = detail.get("quality_label")
    st.markdown(
        f"## {ticker_link_html(ticker)} — {tier_friendly(tier) if tier != 'filtered' else 'No setup'}",
        unsafe_allow_html=True,
    )
    if quality:
        st.caption(f"**Quality grade:** {quality}")

    fail = (data.get("eligibility") or {}).get("fail_reason")
    if fail and not data.get("eligible"):
        label = SWING_FILTER_LABELS.get(fail, data.get("tier_reason", fail))
        st.info(label)

    if not detail.get("close") and not detail.get("rsi"):
        st.warning("No weekly indicator data — price fetch or validation failed for this ticker.")
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "Setup score",
        "—" if swing_score is None else f"{float(swing_score):.0f}",
        help="Base rule credit minus penalties (0–100).",
    )
    c2.metric("Close", f"${detail.get('close', 0):.2f}")
    c3.metric("RSI (14w)", f"{detail.get('rsi', 0):.1f}")
    c4.metric("EMA20", f"{detail.get('ema20', 0):.2f}")
    c5.metric("EMA50", f"{detail.get('ema50', 0):.2f}")

    c6, c7, c8 = st.columns(3)
    c6.metric("ATR", f"{detail.get('atr', 0):.2f}")
    c7.metric("MACD hist", f"{detail.get('macd_hist', 0):.4f}")
    checks_passed = detail.get("checks_passed")
    checks_total = detail.get("checks_total")
    checks_label = (
        f"{checks_passed}/{checks_total}"
        if checks_passed is not None and checks_total
        else "—"
    )
    c8.metric("Rules passed", checks_label)

    rule_breakdown = detail.get("rule_breakdown") or []
    penalties = detail.get("penalties") or []
    if rule_breakdown or penalties:
        st.markdown("#### Score breakdown")
        if base_score is not None:
            st.markdown(f"**Base score:** {float(base_score):.0f} / 100")
        if penalties:
            st.markdown("**Penalties**")
            for item in penalties:
                st.markdown(
                    f"−{abs(float(item.get('amount', 0))):.0f} **{item.get('label', '')}** — "
                    f"{item.get('reason', '')}"
                )
        if penalty_total is not None and float(penalty_total) != 0:
            st.markdown(f"**Net penalties:** {float(penalty_total):.0f}")
        if swing_score is not None:
            st.markdown(f"**Final score:** {float(swing_score):.0f}")

    if rule_breakdown:
        st.markdown("#### Rule partial credit (0–20 each)")
        for item in rule_breakdown:
            passed = item.get("passed")
            badge = "✅" if passed else "◐" if float(item.get("score", 0)) > 0 else "❌"
            pts = item.get("score", 0)
            st.markdown(
                f"{badge} **{item.get('label', item.get('rule', ''))}** — "
                f"{pts:.0f}/{item.get('max', 20):.0f} pts · need: {item.get('threshold', '')}"
            )

    setup_side = "long" if tier == "SETUP_LONG" else "short" if tier == "SETUP_SHORT" else detail.get("candidate_side", "long")
    st.markdown(f"#### Setup rule checklist ({setup_side} side — 5 rules)")
    st.caption(
        "All five checks must pass for a long or short setup. "
        "Non-setups show the side used for scoring."
    )

    checks = data.get("swing_checks") or (data.get("eligibility") or {}).get("checks") or []
    prefix = f"{setup_side}_"
    side_checks = [c for c in checks if str(c.get("rule", "")).startswith(prefix)]
    if not side_checks and checks:
        side_checks = checks[:5]

    if side_checks:
        for check in side_checks:
            passed = check.get("passed")
            badge = "✅" if passed else "❌"
            label = check.get("label") or check.get("rule", "").replace("_", " ").title()
            threshold = check.get("threshold", "")
            value = check.get("value")
            st.markdown(f"{badge} **{label}** — need: {threshold}")
            if value is not None:
                st.caption(f"Actual: {value}")
            if check.get("detail"):
                st.caption(check["detail"])
    else:
        render_eligibility_panel(data)

    other = "short" if setup_side == "long" else "long"
    other_checks = [c for c in checks if str(c.get("rule", "")).startswith(f"{other}_")]
    if other_checks:
        with st.expander(f"Alternate {other} setup rules (not primary)", expanded=False):
            for check in other_checks:
                passed = check.get("passed")
                badge = "✅" if passed else "❌"
                label = check.get("label") or check.get("rule", "")
                st.markdown(f"{badge} **{label}** — {check.get('threshold', '')}")


def render_swing_setups_tab(
    tickers: list[dict],
    filters: SwingFilters,
    *,
    summary: dict,
    repo: ScanRepository,
    universe_id: str,
    scan_date,
) -> None:
    render_swing_takeaway(
        summary=summary,
        repo=repo,
        universe_id=universe_id,
        scan_date=scan_date,
    )
    st.markdown("### Weekly Setups")
    with st.expander("Setup score rubric", expanded=False):
        render_swing_score_guide()
    df = apply_swing_filters(swing_setups_dataframe(tickers), filters)
    if df.empty:
        st.info("No swing setups match the current filters.")
        return
    st.download_button(
        "Download setups CSV",
        df.to_csv(index=False).encode(),
        file_name="swing_setups.csv",
        mime="text/csv",
    )
    display_df = with_yahoo_ticker_links(df)
    display_cols = _swing_display_columns(display_df, setups_only=True)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config=_swing_table_columns(setups_only=True),
        column_order=table_column_order(display_cols),
    )


def render_swing_universe_tab(
    tickers: list[dict],
    filters: SwingFilters,
    *,
    detail_ticker: str | None,
) -> str | None:
    st.markdown("### Full Universe")
    st.caption(
        "Every ticker includes weekly indicators and setup rule results — "
        "click a row for the full calculation breakdown."
    )
    df = swing_universe_dataframe(tickers)
    if filters.search:
        df = df[df["ticker"].str.contains(filters.search, na=False)]
    if df.empty:
        st.warning("No tickers in this scan.")
        return detail_ticker

    table_col, detail_col = st.columns([1.55, 1], gap="large")
    display_df = with_yahoo_ticker_links(df)
    display_cols = _swing_display_columns(display_df)
    with table_col:
        selection = st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="swing_universe_select",
            column_config=_swing_table_columns(),
            column_order=table_column_order(display_cols),
        )
        st.download_button(
            "Download universe CSV",
            df.to_csv(index=False).encode(),
            file_name="swing_universe.csv",
            mime="text/csv",
        )

    active = detail_ticker
    if selection.selection.rows:
        active = df.iloc[selection.selection.rows[0]]["ticker"]
        set_detail_ticker(active)
    elif not active and not df.empty:
        active = df.iloc[0]["ticker"]

    with detail_col:
        st.markdown("##### Selected ticker")
        if active:
            data = get_swing_ticker_by_name(tickers, active)
            if data:
                render_swing_ticker_detail(active, data)
            else:
                st.info("Select a row to view setup calculations.")
        else:
            st.info("Select a row to view setup calculations.")

    return active


def render_swing_detail_tab(
    tickers: list[dict],
    all_symbols: list[str],
    detail_ticker: str | None,
) -> None:
    st.markdown("### Ticker Setup Profile")
    st.caption("Weekly indicators and long/short rule checklist for any ticker in the scan.")
    if not all_symbols:
        st.warning("No tickers in this scan.")
        return
    pick_index = all_symbols.index(detail_ticker) if detail_ticker in all_symbols else 0
    active = st.selectbox("Select ticker", all_symbols, index=pick_index, key="swing_detail_pick")
    if active != detail_ticker:
        set_detail_ticker(active)
    data = get_swing_ticker_by_name(tickers, active)
    if data:
        render_swing_ticker_detail(active, data)
    else:
        st.warning(f"No data for {active}.")


def render_swing_rejection_tab(summary: dict) -> None:
    st.markdown("### Why setups were rejected")
    breakdown = summary.get("filter_breakdown") or {}
    if not breakdown:
        st.info("No rejection breakdown recorded for this scan.")
        return
    from quant_hub.dashboard.viz.components import render_exclusion_chart

    labeled = {
        SWING_FILTER_LABELS.get(k, k.replace("_", " ").title()): v for k, v in breakdown.items()
    }
    fig = render_exclusion_chart(labeled)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    rows = sorted(labeled.items(), key=lambda item: -item[1])
    st.dataframe(
        [{"reason": k, "count": v} for k, v in rows],
        use_container_width=True,
        hide_index=True,
    )
