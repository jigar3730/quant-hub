"""Cross-scan ticker history panel for dashboard."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import streamlit as st

from quant_hub.dashboard.viz.navigation import (
    HISTORY_PAGE_OFFSET_KEY,
    navigate_to_scan,
    ticker_link_html,
)
from quant_hub.dashboard.viz.table_helpers import merge_column_config, table_column_order
from quant_hub.history.ticker_projection import history_display_columns
from quant_hub.infrastructure.postgres.repository import ScanRepository

logger = logging.getLogger(__name__)

HISTORY_PAGE_SIZE = 50


def _row_detail_snapshot(row: dict) -> dict:
    """Key fields for accuracy review in an expander."""
    skip = {
        "run_id",
        "scan_time",
        "strategy_id",
        "strategy_label",
        "ticker",
        "tier",
        "tier_label",
    }
    return {k: v for k, v in row.items() if k not in skip and v is not None}


def render_ticker_history_panel(
    repo: ScanRepository,
    ticker: str,
    *,
    key_prefix: str = "history",
    show_header: bool = True,
) -> None:
    """Paginated scan appearances across all strategies and universes.

    Defaults to every persisted appearance (including filtered/ineligible rows).
    Toggle *Actionable only* to narrow to Launchpad Tier 1/Tier 2 and Lynch passed.
    """
    symbol = ticker.strip().upper()
    if not symbol:
        return

    offset_key = f"{key_prefix}_{HISTORY_PAGE_OFFSET_KEY}"
    if offset_key not in st.session_state:
        st.session_state[offset_key] = 0

    def _reset_offset() -> None:
        st.session_state[offset_key] = 0

    actionable_only = st.checkbox(
        "Actionable only (Launchpad Tier 1/Tier 2 and Lynch passed)",
        value=False,
        key=f"{key_prefix}_actionable_only",
        on_change=_reset_offset,
    )
    offset = int(st.session_state[offset_key])

    try:
        with st.spinner(f"Loading scan history for {symbol}…"):
            total = repo.ticker_history_count(
                symbol,
                actionable_only=actionable_only,
                exclude_fixtures=True,
            )
            rows = repo.ticker_history(
                symbol,
                actionable_only=actionable_only,
                exclude_fixtures=True,
                limit=HISTORY_PAGE_SIZE,
                offset=offset,
            )
            actionable_total = (
                total
                if actionable_only
                else repo.ticker_history_count(
                    symbol, actionable_only=True, exclude_fixtures=True
                )
            )
    except Exception:  # noqa: BLE001 - surface DB failures instead of a false empty state
        logger.exception("Failed to load ticker history for %s", symbol)
        st.error(
            f"Could not load scan history for **{symbol}**. The database may be "
            "unavailable — check the connection and try again."
        )
        return

    if show_header:
        label = "actionable scan history" if actionable_only else "scan history"
        st.markdown(
            f"### {ticker_link_html(symbol)} — {label}",
            unsafe_allow_html=True,
        )

    if total == 0:
        if actionable_only:
            st.info(
                f"No actionable appearances found for **{symbol}**. Uncheck "
                "**Actionable only** to see every scan this ticker appeared in."
            )
        else:
            st.info(
                f"No scan appearances found for **{symbol}** in persisted scan history."
            )
        return

    strategies = sorted({r.get("strategy_label") for r in rows if r.get("strategy_label")})
    strat_note = f" across {', '.join(strategies)}" if strategies else ""
    if actionable_only:
        st.caption(
            f"Showing {offset + 1}–{min(offset + len(rows), total)} of {total} "
            f"actionable appearance(s){strat_note}"
        )
    else:
        st.caption(
            f"Showing {offset + 1}–{min(offset + len(rows), total)} of {total} "
            f"appearance(s){strat_note} ({actionable_total} actionable)"
        )

    display_cols = history_display_columns(rows)
    table_df = pd.DataFrame(rows)
    present_cols = [c for c in display_cols if c in table_df.columns]
    st.dataframe(
        table_df[present_cols],
        use_container_width=True,
        hide_index=True,
        column_config=merge_column_config({
            "scan_date": st.column_config.TextColumn("Date"),
            "strategy_label": st.column_config.TextColumn("Strategy"),
            "universe_id": st.column_config.TextColumn("Universe"),
            "tier_label": st.column_config.TextColumn("Status"),
            "eligible": st.column_config.CheckboxColumn("Eligible"),
            "final_score": st.column_config.NumberColumn("Score", format="%.1f"),
            "filter_reason": st.column_config.TextColumn("Filter reason"),
            "regime_label": st.column_config.TextColumn("Regime"),
            "normalized_score": st.column_config.NumberColumn("Norm", format="%.1f"),
            "lynch_score": st.column_config.NumberColumn("Lynch", format="%.0f"),
            "institutional_pct": st.column_config.NumberColumn("Inst %", format="%.1f"),
            "analyst_count": st.column_config.NumberColumn("Analysts", format="%d"),
            "peg_ratio": st.column_config.NumberColumn("PEG", format="%.2f"),
            "pe_ratio": st.column_config.NumberColumn("P/E", format="%.1f"),
            "categories": st.column_config.TextColumn("Categories"),
        }),
        column_order=table_column_order(present_cols),
    )

    nav_cols = st.columns([1, 1, 4])
    with nav_cols[0]:
        if offset > 0 and st.button("Previous page", key=f"{key_prefix}_prev"):
            st.session_state[offset_key] = max(0, offset - HISTORY_PAGE_SIZE)
            st.rerun()
    with nav_cols[1]:
        if offset + HISTORY_PAGE_SIZE < total and st.button("Next page", key=f"{key_prefix}_next"):
            st.session_state[offset_key] = offset + HISTORY_PAGE_SIZE
            st.rerun()

    st.markdown("#### Open a scan snapshot")
    for idx, row in enumerate(rows):
        label = (
            f"{row['scan_date']} · {row.get('strategy_label')} · {row['universe_id']} · "
            f"{row.get('tier_label')}"
        )
        with st.expander(label, expanded=False):
            st.json(_row_detail_snapshot(row))
            if st.button("Open this scan", key=f"{key_prefix}_open_{idx}_{row['run_id']}"):
                navigate_to_scan(
                    row["strategy_id"],
                    row["universe_id"],
                    date.fromisoformat(str(row["scan_date"])),
                    detail_ticker=symbol,
                )
