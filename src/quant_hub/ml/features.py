"""Flatten scan detail JSON into tabular ML features."""

from __future__ import annotations

from typing import Any

from quant_hub.ml.constants import FEATURE_SCHEMA_VERSION


def _categories_str(categories: list | None) -> str | None:
    if not categories:
        return None
    return ",".join(sorted(str(c) for c in categories))


def _score_from_block(scores: dict, name: str) -> float | None:
    block = scores.get(name)
    if isinstance(block, dict) and "score" in block:
        try:
            return float(block["score"])
        except (TypeError, ValueError):
            return None
    flat = scores.get(f"{name}_score")
    if flat is None:
        return None
    try:
        return float(flat)
    except (TypeError, ValueError):
        return None


def _raw_from_block(scores: dict, name: str, key: str) -> float | None:
    """Pull a numeric field from scores[name].raw (Launchpad factor detail payload)."""
    block = scores.get(name)
    if not isinstance(block, dict):
        return None
    raw = block.get("raw")
    if not isinstance(raw, dict) or key not in raw:
        return None
    try:
        return float(raw[key])
    except (TypeError, ValueError):
        return None


def extract_features(
    *,
    strategy_id: str,
    detail: dict[str, Any],
    run: dict[str, Any],
) -> dict[str, Any]:
    """Build a flat feature row from ticker detail + scan run context."""
    summary = detail.get("summary") or {}
    metadata = run.get("metadata") or {}
    prov = metadata.get("data_provenance") or {}
    eligibility = detail.get("eligibility") or {}

    row: dict[str, Any] = {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "run_id": run["id"],
        "scan_date": str(run["scan_date"]),
        "scan_time": str(run.get("scan_time", "")),
        "strategy_id": strategy_id,
        "universe_id": run["universe_id"],
        "ticker": detail.get("ticker"),
        "tier": detail.get("tier"),
        "eligible": detail.get("eligible"),
        "final_score": summary.get("final_adjusted_score") or detail.get("final_score"),
        "regime_label": run.get("regime_label"),
        "regime_multiplier": run.get("regime_multiplier"),
        "as_of_price": prov.get("as_of_price"),
        "price_cache": prov.get("price_cache"),
        "fundamentals_cache": prov.get("fundamentals_cache"),
        "filter_reason": eligibility.get("fail_reason") or detail.get("filter_reason"),
        "universe_size": run.get("universe_size"),
    }

    if strategy_id == "launchpad":
        # Spec feature names ← live Launchpad payload fields (scores.*.raw / summary).
        scores = detail.get("scores") or {}
        row["final_score"] = (
            summary.get("final_adjusted_score")
            if summary.get("final_adjusted_score") is not None
            else detail.get("final_score")
        )
        row["volatility_compression_ratio"] = _raw_from_block(
            scores, "squeeze_intensity", "squeeze_ratio"
        )
        row["relative_strength_rank"] = _raw_from_block(
            scores, "tightness_percentile", "tightness_rank_pct"
        )
        row["volume_rs_score"] = _raw_from_block(scores, "volume_vacuum_depth", "rvol")
        # Launchpad tracks distance to support/EMA50 (closest analog to resistance distance).
        row["resistance_distance_pct"] = _raw_from_block(
            scores, "trend_proximity_match", "pct_distance"
        )
        row["market_regime_multiplier"] = (
            run.get("regime_multiplier")
            if run.get("regime_multiplier") is not None
            else summary.get("regime_multiplier")
        )
        row["eligible"] = 1.0 if detail.get("eligible") else 0.0
        # Retain factor scores for export diagnostics (not in LAUNCHPAD_FEATURE_COLUMNS).
        row["normalized_score"] = summary.get("normalized_score")
        row["raw_score"] = summary.get("raw_score")
        row["score_squeeze_intensity"] = _score_from_block(scores, "squeeze_intensity")
        row["score_tightness_percentile"] = _score_from_block(scores, "tightness_percentile")
        row["score_volume_vacuum_depth"] = _score_from_block(scores, "volume_vacuum_depth")
        row["score_trend_proximity_match"] = _score_from_block(scores, "trend_proximity_match")
        row["score_macd_zero_line"] = _score_from_block(scores, "macd_zero_line")

    elif strategy_id == "lynch":
        metrics = detail.get("metrics") or {}
        row["lynch_score"] = detail.get("lynch_score")
        row["passed"] = detail.get("passed")
        row["peg_ratio"] = detail.get("peg_ratio") or metrics.get("peg_ratio")
        row["pe_ratio"] = detail.get("pe_ratio") or metrics.get("pe_ratio")
        row["eps_growth_5y_pct"] = metrics.get("eps_growth_5y")
        row["debt_to_equity"] = metrics.get("debt_to_equity")
        row["return_on_equity"] = metrics.get("return_on_equity")
        row["categories"] = _categories_str(detail.get("categories"))
        row["fetch_complete"] = metrics.get("data_quality", {}).get("complete")
        row["fetch_error"] = bool(metrics.get("error")) or detail.get("lynch_score") is None

    return row


def merge_outcome_columns(
    features: dict[str, Any],
    outcome: dict[str, Any] | None,
) -> dict[str, Any]:
    """Attach label columns for a single horizon export row."""
    if not outcome:
        return features
    return {
        **features,
        "horizon_days": outcome.get("horizon_days"),
        "anchor_date": str(outcome.get("anchor_date", "")),
        "forward_return_pct": outcome.get("forward_return_pct"),
        "forward_max_gain_pct": outcome.get("forward_max_gain_pct"),
        "forward_max_drawdown_pct": outcome.get("forward_max_drawdown_pct"),
        "spy_forward_return_pct": outcome.get("spy_forward_return_pct"),
        "excess_return_pct": outcome.get("excess_return_pct"),
        "label_binary": outcome.get("label_binary"),
        "label_status": outcome.get("label_status"),
    }
