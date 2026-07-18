import json
from pathlib import Path

import pandas as pd

from quant_hub.config import PRIMARY_INDEX_UNIVERSE, scan_output_paths
from quant_hub.dashboard.viz.design_tokens import TIER_COLORS
from quant_hub.filters.eligibility import FILTER_LABELS

SCORE_LABELS = {
    "rs_market": "RS vs Market",
    "rs_sector": "RS vs Sector",
    "accumulation": "Accumulation",
    "relative_volume": "Relative Volume",
    "compression": "Compression",
    "pattern": "Pattern",
    "resistance": "Resistance",
}

LAUNCHPAD_SCORE_LABELS = {
    "squeeze_intensity": "Squeeze Intensity",
    "tightness_percentile": "Candle Tightness",
    "volume_vacuum_depth": "Volume Vacuum",
    "trend_proximity_match": "Trend & Proximity",
}

# TIER_COLORS is imported above from design_tokens and re-exported here so existing
# `from quant_hub.dashboard.viz.data import TIER_COLORS` call sites keep working.

TECHNICAL_KEYS = (
    "rs_market",
    "rs_sector",
    "accumulation",
    "relative_volume",
    "compression",
    "pattern",
    "resistance",
)

LAUNCHPAD_TECHNICAL_KEYS = (
    "squeeze_intensity",
    "tightness_percentile",
    "volume_vacuum_depth",
    "trend_proximity_match",
)


def load_report(
    path: Path | str | None = None,
) -> dict:
    path = Path(path or scan_output_paths("breakout", PRIMARY_INDEX_UNIVERSE)["json"])
    with path.open() as f:
        return json.load(f)


def tickers_to_dataframe(tickers: list[dict]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        summary = t.get("summary") or {}
        rows.append(
            {
                "ticker": t["ticker"],
                "eligible": t.get("eligible", False),
                "tier": t.get("tier", "filtered"),
                "sector_etf": t.get("sector_etf"),
                "final_score": summary.get("final_adjusted_score", 0),
                "normalized_score": summary.get("normalized_score", 0),
                "raw_score": summary.get("raw_score", 0),
                "tier_reason": t.get("tier_reason", ""),
                "filter_reason": t.get("eligibility", {}).get("fail_reason"),
            }
        )
    return pd.DataFrame(rows)


def scores_to_dataframe(ticker: dict, *, strategy_id: str = "breakout") -> pd.DataFrame:
    scores = ticker.get("scores") or {}
    labels = LAUNCHPAD_SCORE_LABELS if strategy_id == "launchpad" else SCORE_LABELS
    rows = []
    for key, label in labels.items():
        comp = scores.get(key)
        if not comp:
            continue
        rows.append(
            {
                "component": label,
                "key": key,
                "score": comp.get("score", 0),
                "max": comp.get("max", 0),
                "pct": (comp.get("score", 0) / comp["max"] * 100) if comp.get("max") else 0,
                "meaning": comp.get("meaning", ""),
            }
        )
    return pd.DataFrame(rows)


def _component_total(scores: dict, keys: tuple[str, ...]) -> float | None:
    values = []
    for key in keys:
        comp = scores.get(key)
        if comp and comp.get("score") is not None:
            values.append(float(comp["score"]))
    return round(sum(values), 1) if values else None


def full_universe_dataframe(
    tickers: list[dict],
    *,
    strategy_id: str = "breakout",
) -> pd.DataFrame:
    """Full scan table with summary, component scores, and fundamental metrics."""
    from quant_hub.dashboard.viz.signals import top_signals_short, top_signals_tooltip
    from quant_hub.scoring.launchpad import FILTER_LABELS as LAUNCHPAD_FILTER_LABELS

    score_labels = LAUNCHPAD_SCORE_LABELS if strategy_id == "launchpad" else SCORE_LABELS
    technical_keys = (
        LAUNCHPAD_TECHNICAL_KEYS if strategy_id == "launchpad" else TECHNICAL_KEYS
    )
    filter_labels = LAUNCHPAD_FILTER_LABELS if strategy_id == "launchpad" else FILTER_LABELS

    rows = []
    for t in tickers:
        summary = t.get("summary") or {}
        scores = t.get("scores") or {}
        elig = t.get("eligibility") or {}
        fail_reason = elig.get("fail_reason") or ""
        row: dict = {
            "ticker": t["ticker"],
            "eligible": t.get("eligible", False),
            "tier": t.get("tier", "filtered"),
            "sector_etf": t.get("sector_etf"),
            "final_score": round(summary.get("final_adjusted_score", 0), 1),
            "normalized_score": round(summary.get("normalized_score", 0), 1),
            "raw_score": round(summary.get("raw_score", 0), 1),
            "tier_reason": t.get("tier_reason", ""),
            "top_signal": top_signals_short(scores),
            "signal_tooltip": top_signals_tooltip(scores),
            "tech_score": _component_total(scores, technical_keys),
            "filter_reason": fail_reason,
            "filter_label": filter_labels.get(fail_reason, fail_reason) if fail_reason else "",
        }
        for key, label in score_labels.items():
            comp = scores.get(key)
            row[label] = round(comp.get("score", 0), 1) if comp else None
        rows.append(row)
    return pd.DataFrame(rows).sort_values("final_score", ascending=False)


def score_heatmap_dataframe(
    tickers: list[dict],
    eligible_only: bool = True,
    *,
    strategy_id: str = "breakout",
) -> pd.DataFrame:
    score_labels = LAUNCHPAD_SCORE_LABELS if strategy_id == "launchpad" else SCORE_LABELS
    subset = [t for t in tickers if t.get("eligible")] if eligible_only else tickers
    rows = []
    for t in subset:
        scores = t.get("scores") or {}
        row = {"ticker": t["ticker"]}
        for key, label in score_labels.items():
            comp = scores.get(key, {})
            row[label] = comp.get("score", 0)
        rows.append(row)
    return pd.DataFrame(rows)
