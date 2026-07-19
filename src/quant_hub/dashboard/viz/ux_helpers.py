"""Cross-cutting UX helpers — takeaways, near-misses, navigation."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from quant_hub.config import (
    LAUNCHPAD_TIER1_NORMALIZED_MIN,
    LAUNCHPAD_TIER2_NORMALIZED_MIN,
)
from quant_hub.dashboard.viz.labels import format_report_label, tier_friendly
from quant_hub.dashboard.viz.table_helpers import (
    merge_column_config,
    table_column_order,
    with_yahoo_ticker_links,
)
from quant_hub.infrastructure.postgres.repository import ScanRepository

NEAR_MISS_NORMALIZED_GAP = 5.0
# Sidebar scan-date dropdown + Launchpad/Lynch history lookup
DASHBOARD_RUN_LOOKUP_LIMIT = 500


def scanned_universe_ids(repo: ScanRepository, strategy_id: str) -> set[str]:
    runs = repo.list_runs(strategy_id=strategy_id, limit=100, exclude_fixtures=True)
    return {r["universe_id"] for r in runs}


def sorted_universe_ids(all_ids: list[str], scanned: set[str]) -> list[str]:
    return sorted(all_ids, key=lambda uid: (uid not in scanned, uid))


def near_miss_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Eligible names close to watchlist / high-conviction thresholds."""
    if df.empty:
        return df
    eligible = df[df["eligible"]].copy()
    if eligible.empty:
        return eligible

    normalized_floor = LAUNCHPAD_TIER2_NORMALIZED_MIN - NEAR_MISS_NORMALIZED_GAP
    tier3_near = eligible[
        (eligible["tier"] == "Tier 3") & (eligible["normalized_score"] >= normalized_floor)
    ]
    tier2_almost_t1 = eligible[
        (eligible["tier"] == "Tier 2")
        & (eligible["normalized_score"] >= LAUNCHPAD_TIER1_NORMALIZED_MIN)
    ]

    combined = pd.concat([tier3_near, tier2_almost_t1], ignore_index=True)
    if combined.empty:
        return combined
    return (
        combined.drop_duplicates(subset=["ticker"])
        .sort_values(["normalized_score", "final_score"], ascending=False)
        .reset_index(drop=True)
    )


def render_near_miss_panel(df: pd.DataFrame, *, max_rows: int = 12) -> None:
    near = near_miss_dataframe(df)
    if near.empty:
        return

    st.markdown("#### Near watchlist threshold")
    st.caption(
        f"Eligible names within ~5 points of the watchlist cutoff (normalized "
        f"{LAUNCHPAD_TIER2_NORMALIZED_MIN:.0f}) or high normalized score missing Tier 1 criteria."
    )
    display = near.head(max_rows)[
        ["ticker", "tier", "final_score", "normalized_score", "tier_reason"]
    ].copy()
    display["tier"] = display["tier"].map(lambda t: tier_friendly(t, short=True))
    display = display.rename(
        columns={
            "tier": "Tier",
            "final_score": "Final",
            "normalized_score": "Norm",
            "tier_reason": "Why not actionable",
        }
    )
    display = with_yahoo_ticker_links(display)
    base_cols = [column for column in display.columns if column != "ticker_link"]
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config=merge_column_config(),
        column_order=table_column_order(base_cols),
    )


def render_lynch_takeaway(*, summary: dict, candidate_count: int) -> None:
    passed = int(summary.get("passed_count", candidate_count))
    if passed > 0:
        st.success(f"**Today's takeaway:** {passed} name(s) passed the Lynch screen.")
    else:
        st.warning(
            "**Today's takeaway:** No Lynch candidates passed for this universe/preset. "
            "Try a broader universe or review All Tickers for near-misses."
        )


def render_scan_provenance_footer(
    *,
    strategy_id: str,
    universe_id: str,
    scan_date: date | str | None,
    provenance: dict | None,
) -> None:
    label = format_report_label(
        strategy_id=strategy_id,
        universe_id=universe_id,
        scan_date=scan_date,
    )
    parts = [f"**As of scan:** {label}"]
    if provenance:
        src = provenance.get("price_source") or provenance.get("fundamentals_source")
        if src:
            parts.append(f"Data: {src}")
    st.caption(" · ".join(parts))


def render_disclaimer() -> None:
    st.caption(
        "Screen output is model-based research support, not investment advice. "
        "Verify prices, fundamentals, and news before acting."
    )
