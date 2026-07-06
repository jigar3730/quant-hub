"""Project persisted ticker_results rows into analyst-facing history columns."""

from __future__ import annotations

import json
from typing import Any

_STRATEGY_LABELS = {
    "breakout": "Breakout",
    "swing": "Swing",
    "lynch": "Lynch",
    "mean_reversion": "Mean Reversion",
}

_TIER_LABELS = {
    "Tier 1": "High conv.",
    "Tier 2": "Watchlist",
    "Tier 3": "Monitor",
    "filtered": "Excluded",
    "SETUP_LONG": "Long setup",
    "SETUP_SHORT": "Short setup",
    "HIGH_CONVICTION": "High conv.",
    "WATCHLIST": "Watchlist",
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
    setup = detail_dict.get("setup_detail") or {}
    scores = detail_dict.get("scores") or {}
    trade_plan = setup.get("trade_plan") or {}

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

    if strategy_id == "breakout":
        row.update(
            {
                "normalized_score": summary.get("normalized_score"),
                "final_adjusted_score": summary.get("final_adjusted_score"),
                "tier_reason": detail_dict.get("tier_reason"),
                "rs_market": _score_component(scores, "rs_market"),
                "rs_sector": _score_component(scores, "rs_sector"),
                "compression": _score_component(scores, "compression"),
                "accumulation": _score_component(scores, "accumulation"),
                "relative_volume": _score_component(scores, "relative_volume"),
                "pattern": _score_component(scores, "pattern"),
            }
        )
    elif strategy_id == "swing":
        row.update(
            {
                "setup_type": tier,
                "swing_score": setup.get("swing_score") or summary.get("swing_score"),
                "quality_label": setup.get("quality_label"),
                "rsi": setup.get("rsi") or summary.get("rsi"),
                "rs_percentile": setup.get("rs_percentile"),
                "vol_ratio": setup.get("vol_ratio"),
                "scored_side": setup.get("scored_side"),
                "tier_reason": detail_dict.get("tier_reason"),
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
    elif strategy_id == "mean_reversion":
        row.update(
            {
                "mean_reversion_score": summary.get("mean_reversion_score"),
                "signal": summary.get("signal") or setup.get("signal"),
                "setup_type": summary.get("setup_type") or setup.get("bias"),
                "long_score": summary.get("long_score") or setup.get("long_score"),
                "short_score": summary.get("short_score") or setup.get("short_score"),
                "entry_trigger": trade_plan.get("entry_trigger"),
                "stop_loss": trade_plan.get("stop_loss"),
                "rr_t1": trade_plan.get("rr_t1"),
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
    if "breakout" in strategies:
        extra.extend(["normalized_score", "compression", "accumulation", "rs_market"])
    if "swing" in strategies:
        extra.extend(["swing_score", "quality_label", "rsi", "setup_type"])
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
    if "mean_reversion" in strategies:
        extra.extend(["mean_reversion_score", "signal", "entry_trigger", "stop_loss", "rr_t1"])

    seen: set[str] = set()
    ordered: list[str] = []
    for col in base + extra:
        if col not in seen:
            seen.add(col)
            ordered.append(col)
    return ordered
