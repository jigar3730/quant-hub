"""Launchpad Overview view-model — scan-local insights, no Streamlit."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from quant_hub.config import (
    LAUNCHPAD_TIER1_NORMALIZED_MIN,
    LAUNCHPAD_TIER2_NORMALIZED_MIN,
)
from quant_hub.dashboard.viz.data import LAUNCHPAD_SCORE_LABELS
from quant_hub.dashboard.viz.ux_helpers import NEAR_MISS_NORMALIZED_GAP
from quant_hub.filters.eligibility import FILTER_LABELS
from quant_hub.history.actionable import ACTIONABLE_TIERS

ACTIONABLE_LAUNCHPAD = ACTIONABLE_TIERS["launchpad"]
MACD_IGNITION_SCORE = 25.0
BLOCKED_SCORE_MIN = LAUNCHPAD_TIER2_NORMALIZED_MIN
GRID_ROW_CAP = 30
TOP_CONTRIBUTION_CAP = 12
CONCENTRATION_SHARE = 0.5
CONCENTRATION_MIN_ACTIONABLE = 4

SCORE_FACTORS: tuple[tuple[str, str, float], ...] = (
    ("squeeze_intensity", LAUNCHPAD_SCORE_LABELS["squeeze_intensity"], 40.0),
    ("volume_vacuum_depth", LAUNCHPAD_SCORE_LABELS["volume_vacuum_depth"], 30.0),
    ("tightness_percentile", LAUNCHPAD_SCORE_LABELS["tightness_percentile"], 15.0),
    ("trend_proximity_match", LAUNCHPAD_SCORE_LABELS["trend_proximity_match"], 15.0),
)

TIER_RANK = {
    "filtered": 0,
    "Tier 3": 1,
    "Tier 2": 2,
    "Tier 1": 3,
}

TRADABLE_FAIL_REASONS = frozenset(
    {
        "no_price_data",
        "insufficient_history",
        "invalid_price",
        "price_below_10",
        "volume_below_min",
    }
)
MACRO_FAIL_REASONS = frozenset({"macro_trend_not_aligned"})
PROXIMITY_FAIL_REASONS = frozenset({"structural_proximity"})

GridStatus = Literal["Actionable", "Near miss", "Blocked", "Blocked ≥80"]


def _coerce_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _final_score(ticker: dict) -> float:
    summary = ticker.get("summary") or {}
    return _as_float(summary.get("final_adjusted_score"), _as_float(ticker.get("final_score")))


def _normalized_score(ticker: dict) -> float:
    summary = ticker.get("summary") or {}
    return _as_float(summary.get("normalized_score"))


def _score_block(ticker: dict, key: str) -> dict:
    scores = ticker.get("scores") or {}
    block = scores.get(key)
    return block if isinstance(block, dict) else {}


def _factor_points(ticker: dict, key: str) -> float:
    return _as_float(_score_block(ticker, key).get("score"))


def _raw_field(ticker: dict, key: str, field: str) -> float | None:
    raw = _score_block(ticker, key).get("raw")
    if not isinstance(raw, dict):
        return None
    return _optional_float(raw.get(field))


def _raw_text(ticker: dict, key: str, field: str) -> str | None:
    raw = _score_block(ticker, key).get("raw")
    if not isinstance(raw, dict):
        return None
    value = raw.get(field)
    if value is None:
        return None
    return str(value)


def _fail_reason(ticker: dict) -> str | None:
    eligibility = ticker.get("eligibility") or {}
    reason = eligibility.get("fail_reason") or ticker.get("filter_reason")
    if not reason or reason == "eligible":
        return None
    return str(reason)


def reason_label(code: str | None) -> str:
    if not code:
        return ""
    return FILTER_LABELS.get(code, code.replace("_", " ").title())


def _is_actionable(ticker: dict) -> bool:
    return ticker.get("tier") in ACTIONABLE_LAUNCHPAD


def _is_near_miss(ticker: dict) -> bool:
    if not ticker.get("eligible"):
        return False
    tier = ticker.get("tier")
    norm = _normalized_score(ticker)
    watchlist_floor = LAUNCHPAD_TIER2_NORMALIZED_MIN - NEAR_MISS_NORMALIZED_GAP
    if tier == "Tier 3" and norm >= watchlist_floor:
        return True
    if tier == "Tier 2" and norm >= LAUNCHPAD_TIER1_NORMALIZED_MIN:
        return True
    return False


def _is_blocked(ticker: dict) -> bool:
    return not ticker.get("eligible") and _final_score(ticker) >= BLOCKED_SCORE_MIN


def _macd_ignition(ticker: dict) -> bool:
    return _factor_points(ticker, "macd_zero_line") >= MACD_IGNITION_SCORE


def _top_factor(ticker: dict) -> str:
    ranked: list[tuple[float, str]] = []
    for key, label, max_pts in SCORE_FACTORS:
        if max_pts <= 0:
            continue
        ranked.append((_factor_points(ticker, key) / max_pts, label))
    if not ranked:
        return ""
    ranked.sort(reverse=True)
    return ranked[0][1]


def _grid_status(ticker: dict) -> GridStatus | None:
    if _is_actionable(ticker):
        return "Actionable"
    if _is_near_miss(ticker):
        return "Near miss"
    if _is_blocked(ticker):
        if _final_score(ticker) >= LAUNCHPAD_TIER1_NORMALIZED_MIN:
            return "Blocked ≥80"
        return "Blocked"
    return None


def _display_reason(ticker: dict) -> str:
    if ticker.get("eligible"):
        return str(ticker.get("tier_reason") or "")
    return str(ticker.get("tier_reason") or reason_label(_fail_reason(ticker)))


def score_grid_row(ticker: dict, *, prior: dict | None = None) -> dict[str, Any]:
    status = _grid_status(ticker)
    prior_score = _final_score(prior) if prior else None
    current_score = _final_score(ticker)
    return {
        "ticker": ticker["ticker"],
        "status": status or "Other",
        "tier": ticker.get("tier") or "filtered",
        "eligible": bool(ticker.get("eligible")),
        "near_miss": _is_near_miss(ticker),
        "blocked_setup": _is_blocked(ticker),
        "final_score": round(current_score, 1),
        "normalized_score": round(_normalized_score(ticker), 1),
        "score_delta": (
            round(current_score - prior_score, 1) if prior_score is not None else None
        ),
        "squeeze_pts": round(_factor_points(ticker, "squeeze_intensity"), 1),
        "tightness_pts": round(_factor_points(ticker, "tightness_percentile"), 1),
        "volume_pts": round(_factor_points(ticker, "volume_vacuum_depth"), 1),
        "trend_pts": round(_factor_points(ticker, "trend_proximity_match"), 1),
        "macd_pts": round(_factor_points(ticker, "macd_zero_line"), 1),
        "macd_ignition": _macd_ignition(ticker),
        "macd_phase": _raw_text(ticker, "macd_zero_line", "phase"),
        "squeeze_ratio": _raw_field(ticker, "squeeze_intensity", "squeeze_ratio"),
        "tightness_rank_pct": _raw_field(ticker, "tightness_percentile", "tightness_rank_pct"),
        "rvol": _raw_field(ticker, "volume_vacuum_depth", "rvol"),
        "ema50_distance_pct": _raw_field(ticker, "trend_proximity_match", "pct_distance"),
        "sector_etf": ticker.get("sector_etf"),
        "top_factor": _top_factor(ticker),
        "filter_reason": _fail_reason(ticker),
        "filter_label": reason_label(_fail_reason(ticker)),
        "reason": _display_reason(ticker),
    }


def _sort_by_score(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (-row["final_score"], row["ticker"]))


def _sort_by_coil(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple:
        squeeze = row["squeeze_ratio"]
        tightness = row["tightness_rank_pct"]
        return (
            squeeze is None,
            squeeze if squeeze is not None else 99.0,
            tightness is None,
            tightness if tightness is not None else 99.0,
            -row["final_score"],
            row["ticker"],
        )

    return sorted(rows, key=key)


def _cap(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return rows[:GRID_ROW_CAP]


def _index_tickers(tickers: list[dict]) -> dict[str, dict]:
    return {row["ticker"]: row for row in tickers if row.get("ticker")}


def _fail_reason_counts(tickers: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ticker in tickers:
        if ticker.get("eligible"):
            continue
        reason = _fail_reason(ticker) or "unknown"
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _reason_entries(counts: dict[str, int], codes: set[str]) -> list[tuple[str, str, int]]:
    rows = [
        (code, reason_label(code), counts[code])
        for code in codes
        if counts.get(code)
    ]
    rows.sort(key=lambda item: (-item[2], item[0]))
    return rows


def _stage(
    *,
    stage_id: str,
    label: str,
    previous_remaining: int,
    dropped: int,
    reasons: list[tuple[str, str, int]],
) -> dict[str, Any]:
    remaining = max(0, previous_remaining - dropped)
    drop_pct = (dropped / previous_remaining) if previous_remaining else 0.0
    conversion = (remaining / previous_remaining) if previous_remaining else 0.0
    return {
        "id": stage_id,
        "label": label,
        "remaining": remaining,
        "dropped": dropped,
        "drop_pct": drop_pct,
        "conversion_pct": conversion,
        "reasons": reasons,
    }


def build_universe_funnel(tickers: list[dict], summary: dict) -> dict[str, Any]:
    universe_size = int(summary.get("universe_size") or len(tickers))
    counts = _fail_reason_counts(tickers)
    known = TRADABLE_FAIL_REASONS | MACRO_FAIL_REASONS | PROXIMITY_FAIL_REASONS
    unknown_codes = {code for code in counts if code not in known}
    tradable_codes = set(TRADABLE_FAIL_REASONS) | unknown_codes

    tradable_drop = sum(counts.get(code, 0) for code in tradable_codes)
    macro_drop = sum(counts.get(code, 0) for code in MACRO_FAIL_REASONS)
    proximity_drop = sum(counts.get(code, 0) for code in PROXIMITY_FAIL_REASONS)

    universe = {
        "id": "universe",
        "label": "Universe",
        "remaining": universe_size,
        "dropped": 0,
        "drop_pct": 0.0,
        "conversion_pct": 1.0,
        "reasons": [],
    }
    tradable = _stage(
        stage_id="tradable",
        label="Tradable",
        previous_remaining=universe_size,
        dropped=tradable_drop,
        reasons=_reason_entries(counts, tradable_codes),
    )
    macro = _stage(
        stage_id="macro",
        label="Macro aligned",
        previous_remaining=tradable["remaining"],
        dropped=macro_drop,
        reasons=_reason_entries(counts, set(MACRO_FAIL_REASONS)),
    )
    eligible = _stage(
        stage_id="eligible",
        label="Eligible",
        previous_remaining=macro["remaining"],
        dropped=proximity_drop,
        reasons=_reason_entries(counts, set(PROXIMITY_FAIL_REASONS)),
    )

    t1 = sum(1 for t in tickers if t.get("tier") == "Tier 1")
    t2 = sum(1 for t in tickers if t.get("tier") == "Tier 2")
    watchlist_remaining = t1 + t2
    watchlist_drop = max(0, eligible["remaining"] - watchlist_remaining)
    watchlist = {
        "id": "watchlist",
        "label": "Watchlist",
        "remaining": watchlist_remaining,
        "dropped": watchlist_drop,
        "drop_pct": (watchlist_drop / eligible["remaining"]) if eligible["remaining"] else 0.0,
        "conversion_pct": (
            (watchlist_remaining / eligible["remaining"]) if eligible["remaining"] else 0.0
        ),
        "reasons": [("below_watchlist", "Normalized score below watchlist (65)", watchlist_drop)]
        if watchlist_drop
        else [],
    }
    t1_drop = t2
    high_conviction = {
        "id": "tier1",
        "label": "High conviction",
        "remaining": t1,
        "dropped": t1_drop,
        "drop_pct": (t1_drop / watchlist_remaining) if watchlist_remaining else 0.0,
        "conversion_pct": (t1 / watchlist_remaining) if watchlist_remaining else 0.0,
        "reasons": [("macd_or_norm", "Missing MACD ignition or norm < 80", t1_drop)]
        if t1_drop
        else [],
    }
    return {
        "universe_size": universe_size,
        "stages": [universe, tradable, macro, eligible, watchlist, high_conviction],
    }


def build_factor_mix(actionable: list[dict]) -> list[dict[str, Any]]:
    size = len(actionable)
    rows: list[dict[str, Any]] = []
    for key, label, max_pts in SCORE_FACTORS:
        points = [_factor_points(ticker, key) for ticker in actionable]
        mean_points = sum(points) / size if size else 0.0
        mean_score = (
            sum(_final_score(ticker) for ticker in actionable) / size if size else 0.0
        )
        rows.append(
            {
                "key": key,
                "label": label,
                "max_points": max_pts,
                "mean_points": round(mean_points, 1),
                "share_of_mean_score": (mean_points / mean_score) if mean_score else 0.0,
                "pct_of_max": (mean_points / max_pts) if max_pts else 0.0,
                "names_at_full": sum(1 for value in points if value >= max_pts),
                "names_at_zero": sum(1 for value in points if value <= 0),
            }
        )
    return rows


def build_contributions(actionable: list[dict]) -> list[dict[str, Any]]:
    ranked = sorted(
        actionable,
        key=lambda ticker: (-_final_score(ticker), ticker.get("ticker") or ""),
    )
    rows: list[dict[str, Any]] = []
    for ticker in ranked[:TOP_CONTRIBUTION_CAP]:
        parts = {key: round(_factor_points(ticker, key), 1) for key, _, _ in SCORE_FACTORS}
        rows.append(
            {
                "ticker": ticker["ticker"],
                "tier": ticker.get("tier"),
                "final_score": round(_final_score(ticker), 1),
                "parts": parts,
                "macd_ignition": _macd_ignition(ticker),
                "top_factor": _top_factor(ticker),
            }
        )
    return rows


def _tier_of(ticker: dict) -> str:
    return str(ticker.get("tier") or "filtered")


def build_scan_delta(
    tickers: list[dict],
    prior_tickers: list[dict] | None,
    *,
    scan_date: str | None,
    prior_date: str | None,
    universe_id: str | None,
) -> dict[str, Any]:
    current_by = _index_tickers(tickers)
    prior_by = _index_tickers(prior_tickers or [])
    current_actionable = {sym for sym, row in current_by.items() if _is_actionable(row)}
    prior_actionable = {sym for sym, row in prior_by.items() if _is_actionable(row)}

    def row_for(symbol: str) -> dict[str, Any]:
        current = current_by.get(symbol)
        prior = prior_by.get(symbol)
        live = current or prior or {}
        from_score = _final_score(prior) if prior else None
        to_score = _final_score(current) if current else None
        return {
            "ticker": symbol,
            "from_tier": _tier_of(prior) if prior else None,
            "to_tier": _tier_of(current) if current else None,
            "from_score": round(from_score, 1) if from_score is not None and prior else None,
            "to_score": round(to_score, 1) if to_score is not None and current else None,
            "score_delta": (
                round(to_score - from_score, 1)
                if current is not None and prior is not None
                else None
            ),
            "from_eligible": bool(prior.get("eligible")) if prior else None,
            "to_eligible": bool(current.get("eligible")) if current else False,
            "drop_reason": _display_reason(current) if current and not current.get("eligible") else (
                _display_reason(current) if current else _display_reason(prior or {})
            ),
            "sector_etf": live.get("sector_etf"),
            "macd_ignition": _macd_ignition(live) if live else False,
        }

    new_actionable = [row_for(sym) for sym in sorted(current_actionable - prior_actionable)]
    dropped = [row_for(sym) for sym in sorted(prior_actionable - current_actionable)]
    upgraded: list[dict[str, Any]] = []
    downgraded: list[dict[str, Any]] = []
    persisted: list[dict[str, Any]] = []
    for symbol in sorted(set(current_by) & set(prior_by)):
        current_rank = TIER_RANK.get(_tier_of(current_by[symbol]), 0)
        prior_rank = TIER_RANK.get(_tier_of(prior_by[symbol]), 0)
        if current_rank > prior_rank:
            upgraded.append(row_for(symbol))
        elif current_rank < prior_rank:
            downgraded.append(row_for(symbol))
        if symbol in current_actionable and symbol in prior_actionable:
            persisted.append(row_for(symbol))

    return {
        "scan_date": scan_date,
        "prior_date": prior_date,
        "universe_id": universe_id,
        "new_actionable": new_actionable,
        "dropped_actionable": dropped,
        "upgraded": upgraded,
        "downgraded": downgraded,
        "persisted": persisted,
    }


def build_sector_matrix(tickers: list[dict]) -> dict[str, Any]:
    tiers = ["Tier 1", "Tier 2", "Tier 3", "filtered"]
    buckets: dict[tuple[str, str], list[float]] = {}
    for ticker in tickers:
        sector = ticker.get("sector_etf") or "—"
        tier = _tier_of(ticker)
        if tier not in tiers:
            tier = "filtered"
        buckets.setdefault((sector, tier), []).append(_final_score(ticker))

    sectors = sorted({sector for sector, _ in buckets})
    cells = [
        {
            "sector_etf": sector,
            "tier": tier,
            "count": len(scores),
            "mean_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        }
        for (sector, tier), scores in sorted(buckets.items())
    ]

    actionable = [t for t in tickers if _is_actionable(t)]
    sector_counts: dict[str, int] = {}
    for ticker in actionable:
        sector = ticker.get("sector_etf") or "—"
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
    dominant_sector = None
    dominant_share = 0.0
    if sector_counts:
        dominant_sector = max(sector_counts, key=lambda key: (sector_counts[key], key))
        dominant_share = sector_counts[dominant_sector] / len(actionable)
    warning = (
        dominant_share >= CONCENTRATION_SHARE
        and len(actionable) >= CONCENTRATION_MIN_ACTIONABLE
    )
    return {
        "sectors": sectors,
        "tiers": tiers,
        "cells": cells,
        "dominant_sector": dominant_sector,
        "dominant_actionable_share": dominant_share,
        "concentration_warning": warning,
    }


def _headline(
    *,
    actionable_count: int,
    regime_label: str | None,
    factor_mix: list[dict[str, Any]],
    prior_date: str | None,
    new_count: int,
    dropped_count: int,
    blocked_high: list[dict[str, Any]],
    dominant_sector: str | None,
    dominant_share: float,
) -> str:
    regime = (regime_label or "unknown").replace("_", " ").lower()
    noun = "name" if actionable_count == 1 else "names"
    parts = [f"{actionable_count} actionable {noun} in {regime}"]

    if factor_mix and actionable_count:
        top = max(factor_mix, key=lambda row: (row["mean_points"], row["max_points"]))
        parts.append(
            f"{top['label'].lower()} is the dominant factor "
            f"({top['mean_points']:.0f}/{top['max_points']:.0f})"
        )
    if prior_date:
        parts.append(f"{new_count} new, {dropped_count} dropped vs {prior_date}")
    if blocked_high:
        first = blocked_high[0]
        gate = first.get("filter_label") or first.get("reason") or "failed a gate"
        if len(blocked_high) == 1:
            parts.append(f"1 blocked setup ≥80 ({first['ticker']} — {gate})")
        else:
            names = ", ".join(row["ticker"] for row in blocked_high[:3])
            parts.append(f"{len(blocked_high)} blocked setups ≥80 ({names})")
    if dominant_sector and dominant_sector != "—" and actionable_count:
        parts.append(f"{dominant_sector} is {dominant_share:.0%} of the book")
    return "; ".join(parts) + "."


def load_prior_report(
    repo: Any,
    *,
    strategy_id: str,
    universe_id: str | None,
    scan_date: date | str | None,
) -> dict[str, Any] | None:
    """Latest same-strategy, same-universe report before ``scan_date``."""
    if repo is None or not universe_id:
        return None
    current = _coerce_date(scan_date)
    if current is None:
        return None
    runs = repo.list_runs_filtered(
        strategy_id=strategy_id,
        universe_id=universe_id,
        until=current,
        limit=10,
    )
    prior = next(
        (run for run in runs if _coerce_date(run.get("scan_date")) is not None
         and _coerce_date(run.get("scan_date")) < current),
        None,
    )
    if not prior:
        return None
    return repo.load_report(
        strategy_id=strategy_id,
        universe_id=universe_id,
        scan_date=_coerce_date(prior["scan_date"]),
        exclude_fixtures=True,
    )


def build_launchpad_overview_vm(
    report: dict[str, Any],
    prior_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble Overview payloads from the current (and optional prior) scan report."""
    summary = report.get("scan_summary") or {}
    regime = report.get("market_regime") or {}
    tickers = list(report.get("tickers") or [])
    prior_tickers = list((prior_report or {}).get("tickers") or [])
    prior_by = _index_tickers(prior_tickers)
    scan_date = str(report.get("scan_date") or "")
    universe_id = str(report.get("universe_id") or "")
    prior_date = str(prior_report["scan_date"]) if prior_report and prior_report.get("scan_date") else None

    actionable = [t for t in tickers if _is_actionable(t)]
    factor_mix = build_factor_mix(actionable)
    contributions = build_contributions(actionable)
    funnel = build_universe_funnel(tickers, summary)
    delta = build_scan_delta(
        tickers,
        prior_tickers or None,
        scan_date=scan_date or None,
        prior_date=prior_date,
        universe_id=universe_id or None,
    )
    sector = build_sector_matrix(tickers)

    grid_rows = [
        score_grid_row(ticker, prior=prior_by.get(ticker["ticker"]))
        for ticker in tickers
        if ticker.get("ticker")
    ]
    actionable_rows = _cap(_sort_by_score([r for r in grid_rows if r["status"] == "Actionable"]))
    near_miss_rows = _cap(_sort_by_score([r for r in grid_rows if r["status"] == "Near miss"]))
    blocked_rows = _cap(
        _sort_by_score([r for r in grid_rows if r["status"] in {"Blocked", "Blocked ≥80"}])
    )
    coil_pool = [r for r in grid_rows if r["status"] in {"Actionable", "Near miss", "Blocked", "Blocked ≥80"}]
    coil_rows = _cap(_sort_by_coil(coil_pool))
    blocked_high = [r for r in blocked_rows if r["final_score"] >= LAUNCHPAD_TIER1_NORMALIZED_MIN]

    dominant_factor = ""
    if factor_mix and actionable:
        dominant_factor = max(factor_mix, key=lambda row: row["mean_points"])["label"]

    takeaway = {
        "headline": _headline(
            actionable_count=len(actionable),
            regime_label=regime.get("label"),
            factor_mix=factor_mix,
            prior_date=prior_date,
            new_count=len(delta["new_actionable"]),
            dropped_count=len(delta["dropped_actionable"]),
            blocked_high=blocked_high,
            dominant_sector=sector["dominant_sector"],
            dominant_share=sector["dominant_actionable_share"],
        ),
        "universe_size": int(summary.get("universe_size") or len(tickers)),
        "eligible_count": int(summary.get("eligible_count") or sum(1 for t in tickers if t.get("eligible"))),
        "actionable_count": len(actionable),
        "tier1_count": sum(1 for t in tickers if t.get("tier") == "Tier 1"),
        "new_count": len(delta["new_actionable"]),
        "dropped_count": len(delta["dropped_actionable"]),
        "upgrade_count": len(delta["upgraded"]),
        "blocked_count": len(blocked_rows),
        "blocked_high_count": len(blocked_high),
        "dominant_factor": dominant_factor,
        "dominant_sector": sector["dominant_sector"],
        "prior_date": prior_date,
        "macd_ignition_count": sum(1 for t in actionable if _macd_ignition(t)),
    }

    return {
        "context": {
            "strategy_id": report.get("strategy_id") or "launchpad",
            "universe_id": universe_id,
            "scan_date": scan_date,
            "regime_label": regime.get("label"),
        },
        "takeaway": takeaway,
        "drivers": {
            "cohort": "actionable",
            "cohort_size": len(actionable),
            "scan_date": scan_date,
            "universe_id": universe_id,
            "factor_mix": factor_mix,
            "top_contributions": contributions,
            "macd_ignition_count": takeaway["macd_ignition_count"],
        },
        "funnel": funnel,
        "delta": delta,
        "sector": sector,
        "grid": {
            "actionable": actionable_rows,
            "near_miss": near_miss_rows,
            "blocked": blocked_rows,
            "coils": coil_rows,
        },
    }
