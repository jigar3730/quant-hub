"""Cross-cutting UX helpers — takeaways, near-misses, navigation."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from quant_hub.dashboard.viz.labels import format_report_label, tier_friendly
from quant_hub.dashboard.viz.navigation import navigate_to
from quant_hub.dashboard.viz.table_helpers import (
    merge_column_config,
    table_column_order,
    with_yahoo_ticker_links,
)
from quant_hub.infrastructure.postgres.repository import ScanRepository

NEAR_MISS_NORMALIZED_GAP = 5.0
NEAR_MISS_FINAL_GAP = 5.0
# Sidebar scan-date dropdown + cross-strategy lookup (covers ~10y weekly backfill)
DASHBOARD_RUN_LOOKUP_LIMIT = 500


def scanned_universe_ids(repo: ScanRepository, strategy_id: str) -> set[str]:
    runs = repo.list_runs(strategy_id=strategy_id, limit=100, exclude_fixtures=True)
    return {r["universe_id"] for r in runs}


def sorted_universe_ids(all_ids: list[str], scanned: set[str]) -> list[str]:
    return sorted(all_ids, key=lambda uid: (uid not in scanned, uid))


def cross_strategy_snapshot(
    repo: ScanRepository,
    *,
    universe_id: str,
    scan_date: date | None,
) -> dict[str, dict | None]:
    """Latest run summary per strategy for the same universe (and date when set)."""
    out: dict[str, dict | None] = {}
    for strategy_id in ("breakout", "swing", "lynch"):
        runs = [
            r
            for r in repo.list_runs(
                strategy_id=strategy_id,
                limit=DASHBOARD_RUN_LOOKUP_LIMIT,
                exclude_fixtures=True,
            )
            if r["universe_id"] == universe_id
        ]
        if scan_date is not None:
            date_s = str(scan_date)
            runs = [r for r in runs if str(r["scan_date"]) == date_s]
        out[strategy_id] = runs[0] if runs else None
    return out


def near_miss_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Eligible names close to watchlist / high-conviction thresholds."""
    if df.empty:
        return df
    eligible = df[df["eligible"]].copy()
    if eligible.empty:
        return eligible

    normalized_floor = 65.0 - NEAR_MISS_NORMALIZED_GAP
    tier3_near = eligible[
        (eligible["tier"] == "Tier 3") & (eligible["normalized_score"] >= normalized_floor)
    ]
    tier2_almost_t1 = eligible[
        (eligible["tier"] == "Tier 2") & (eligible["normalized_score"] >= 80)
    ]
    final_floor = 70.0 - NEAR_MISS_FINAL_GAP
    tier2_final_gap = eligible[
        (eligible["tier"] == "Tier 2")
        & (eligible["normalized_score"] >= 65)
        & (eligible["final_score"] >= final_floor)
        & (eligible["final_score"] < 70)
    ]

    combined = pd.concat([tier3_near, tier2_almost_t1, tier2_final_gap], ignore_index=True)
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
        "Eligible names within ~5 points of the watchlist cutoff (normalized 65) "
        "or high normalized score missing Tier 1 criteria."
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


def _render_cross_strategy_buttons(
    repo: ScanRepository,
    *,
    universe_id: str,
    scan_date: date | None,
    current_strategy: str,
    key_prefix: str,
) -> None:
    snap = cross_strategy_snapshot(repo, universe_id=universe_id, scan_date=scan_date)
    cols = st.columns(3)
    labels = {
        "breakout": "Breakout",
        "swing": "Swing",
        "lynch": "Lynch",
    }
    for col, (strategy_id, label) in zip(cols, labels.items(), strict=True):
        run = snap.get(strategy_id)
        if strategy_id == current_strategy:
            col.caption(f"**{label}** (current)")
            continue
        if not run:
            col.button(
                f"{label} — no scan",
                disabled=True,
                key=f"{key_prefix}_nav_{strategy_id}",
            )
            continue
        if strategy_id == "breakout":
            count = (run.get("tier1_count") or 0) + (run.get("tier2_count") or 0)
            detail = f"{count} actionable"
        elif strategy_id == "swing":
            count = run.get("actionable_count") or 0
            detail = f"{count} setups"
        else:
            count = run.get("actionable_count") or 0
            detail = f"{count} passed"
        if col.button(
            f"Open {label} ({detail})",
            key=f"{key_prefix}_nav_{strategy_id}",
        ):
            navigate_to(strategy_id, universe_id)


def render_breakout_takeaway(
    *,
    summary: dict,
    regime: dict,
    df: pd.DataFrame,
    repo: ScanRepository,
    universe_id: str,
    scan_date: date | None,
    key_prefix: str = "takeaway",
) -> None:
    tiers = summary.get("tier_counts", {})
    actionable = int(tiers.get("Tier 1", 0)) + int(tiers.get("Tier 2", 0))
    eligible = int(summary.get("eligible_count", 0))
    regime_label = regime.get("label", "unknown").title()
    multiplier = regime.get("multiplier", 1.0)

    if actionable > 0:
        st.success(
            f"**Today's takeaway:** {actionable} high-conviction / watchlist name(s) "
            f"in this scan ({eligible} eligible). Regime: {regime_label} (×{multiplier})."
        )
        return

    st.warning(
        f"**Today's takeaway:** No high-conviction or watchlist names in this scan "
        f"({eligible} eligible, {tiers.get('Tier 3', 0)} in monitor tier). "
        f"Regime is **{regime_label}** (×{multiplier}) — scores are discounted in weak markets."
    )
    st.markdown(
        "Review **near-miss** names below, relax sidebar filters, or check another strategy "
        "for the same universe."
    )
    render_near_miss_panel(df)
    _render_cross_strategy_buttons(
        repo,
        universe_id=universe_id,
        scan_date=scan_date,
        current_strategy="breakout",
        key_prefix=key_prefix,
    )


def render_swing_takeaway(
    *,
    summary: dict,
    repo: ScanRepository,
    universe_id: str,
    scan_date: date | None,
) -> None:
    setups = int(summary.get("eligible_count", 0))
    longs = summary.get("setup_long_count", summary.get("tier_counts", {}).get("SETUP_LONG", 0))
    shorts = summary.get("setup_short_count", summary.get("tier_counts", {}).get("SETUP_SHORT", 0))
    if setups > 0:
        st.success(
            f"**Today's takeaway:** {setups} weekly setup(s) — {longs} long, {shorts} short."
        )
    else:
        st.warning(
            "**Today's takeaway:** No weekly setups in this scan. "
            "Check rejection breakdown or try another universe."
        )
        _render_cross_strategy_buttons(
            repo,
            universe_id=universe_id,
            scan_date=scan_date,
            current_strategy="swing",
            key_prefix="swing_takeaway",
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
