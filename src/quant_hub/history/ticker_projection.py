"""Project persisted ticker_results rows into analyst-facing history columns."""

from __future__ import annotations

import json
from typing import Any

_STRATEGY_LABELS = {
    "launchpad": "Launchpad",
    "lynch": "Lynch",
}

_TIER_LABELS = {
    "Tier 1": "High conv.",
    "Tier 2": "Watchlist",
    "Tier 3": "Monitor",
    "filtered": "Excluded",
    "fast_grower": "Fast grower",
    "stalwart": "Stalwart",
    "asset_play": "Asset play",
    "passed": "Passed",
}


def _strategy_label(strategy_id: str) -> str:
    return _STRATEGY_LABELS.get(strategy_id, strategy_id.replace("_", " ").title())


def _tier_label(tier: str) -> str:
    return _TIER_LABELS.get(tier, tier.replace("_", " ").title())


def _parse_detail(detail: Any) -> dict[str, Any]:
    if detail is None:
        return {}
    if isinstance(detail, str):
        return json.loads(detail)
    if isinstance(detail, dict):
        return detail
    return {}


def _score_component(scores: dict | None, key: str) -> float | None:
    if not scores:
        return None
    comp = scores.get(key) or {}
    value = comp.get("score")
    return float(value) if value is not None else None


def _nested_get(data: dict, *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def project_row(
    *,
    run_id: int,
    scan_date: Any,
    scan_time: Any,
    strategy_id: str,
    universe_id: str,
    regime_label: str | None,
    regime_multiplier: float | None,
    ticker: str,
    eligible: bool | None,
    tier: str | None,
    sector_etf: str | None,
    final_score: float | None,
    filter_reason: str | None,
    detail: Any,
) -> dict[str, Any]:
    """Flatten one history row with strategy-specific analyst fields."""
    detail_dict = _parse_detail(detail)
    summary = detail_dict.get("summary") or {}
    scores = detail_dict.get("scores") or {}

    row: dict[str, Any] = {
        "run_id": run_id,
        "scan_date": str(scan_date),
        "scan_time": str(scan_time) if scan_time is not None else None,
        "strategy_id": strategy_id,
        "strategy_label": _strategy_label(strategy_id),
        "universe_id": universe_id,
        "ticker": ticker,
        "tier": tier,
        "tier_label": _tier_label(tier) if tier else None,
        "eligible": eligible,
        "filter_reason": filter_reason or _nested_get(detail_dict, "eligibility", "fail_reason"),
        "sector_etf": sector_etf or detail_dict.get("sector_etf"),
        "regime_label": regime_label,
        "regime_multiplier": regime_multiplier,
        "final_score": final_score if final_score is not None else summary.get("final_adjusted_score"),
    }

    if strategy_id == "launchpad":
        row.update(
            {
                "normalized_score": summary.get("normalized_score"),
                "final_adjusted_score": summary.get("final_adjusted_score"),
                "tier_reason": detail_dict.get("tier_reason"),
                "macd_zero_line": _score_component(scores, "macd_zero_line"),
                "squeeze_intensity": _score_component(scores, "squeeze_intensity"),
                "tightness_percentile": _score_component(scores, "tightness_percentile"),
            }
        )
    elif strategy_id == "lynch":
        metrics = detail_dict.get("metrics") or {}
        cats = detail_dict.get("categories") or []
        row.update(
            {
                "lynch_score": detail_dict.get("lynch_score"),
                "passed": detail_dict.get("passed"),
                "categories": ", ".join(cats) if cats else None,
                "company_name": detail_dict.get("company_name"),
                "sector": detail_dict.get("sector"),
                "pe_ratio": detail_dict.get("pe_ratio"),
                "peg_ratio": detail_dict.get("peg_ratio"),
                "eps_growth_5y_pct": detail_dict.get("eps_growth_5y_pct"),
                "debt_to_equity": detail_dict.get("debt_to_equity"),
                "institutional_pct": detail_dict.get("institutional_pct"),
                "analyst_count": detail_dict.get("analyst_count"),
                "market_cap": detail_dict.get("market_cap"),
                "dividend_yield": detail_dict.get("dividend_yield"),
                "price_to_book": detail_dict.get("price_to_book"),
                "net_cash": detail_dict.get("net_cash"),
                "data_status": "unavailable" if metrics.get("error") else "ok",
                "tier_reason": detail_dict.get("tier_reason"),
            }
        )
    return row


def history_display_columns(rows: list[dict[str, Any]]) -> list[str]:
    """Pick dataframe columns based on strategies present in history rows."""
    base = [
        "scan_date",
        "strategy_label",
        "universe_id",
        "tier_label",
        "final_score",
        "regime_label",
    ]
    strategies = {r.get("strategy_id") for r in rows}
    extra: list[str] = []
    if "launchpad" in strategies:
        extra.extend(["normalized_score", "squeeze_intensity", "tightness_percentile"])
    if "lynch" in strategies:
        extra.extend(
            [
                "lynch_score",
                "institutional_pct",
                "analyst_count",
                "peg_ratio",
                "pe_ratio",
                "categories",
            ]
        )
    seen: set[str] = set()
    ordered: list[str] = []
    for col in base + extra:
        if col not in seen:
            seen.add(col)
            ordered.append(col)
    return ordered
