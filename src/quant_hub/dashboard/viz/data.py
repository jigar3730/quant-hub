import json
from pathlib import Path

import pandas as pd

from quant_hub.config import DEFAULT_OUTPUT_JSON
from quant_hub.filters.eligibility import FILTER_LABELS

SCORE_LABELS = {
    "rs_market": "RS vs Market",
    "rs_sector": "RS vs Sector",
    "accumulation": "Accumulation",
    "relative_volume": "Relative Volume",
    "compression": "Compression",
    "pattern": "Pattern",
    "resistance": "Resistance",
    "revenue": "Revenue",
    "eps": "EPS",
}

TIER_COLORS = {
    "Tier 1": "#22c55e",
    "Tier 2": "#eab308",
    "Tier 3": "#94a3b8",
    "filtered": "#ef4444",
}

TECHNICAL_KEYS = (
    "rs_market",
    "rs_sector",
    "accumulation",
    "relative_volume",
    "compression",
    "pattern",
    "resistance",
)

FUNDAMENTAL_KEYS = ("revenue", "eps")


def load_report(path: Path | str = DEFAULT_OUTPUT_JSON) -> dict:
    path = Path(path)
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


def scores_to_dataframe(ticker: dict) -> pd.DataFrame:
    scores = ticker.get("scores") or {}
    rows = []
    for key, label in SCORE_LABELS.items():
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


def _top_signal(scores: dict) -> str:
    if not scores:
        return ""
    best_key = ""
    best_score = -1.0
    for key, comp in scores.items():
        if not comp:
            continue
        score = float(comp.get("score", 0))
        if score > best_score:
            best_score = score
            best_key = key
    if best_score < 0 or not best_key:
        return ""
    return f"{SCORE_LABELS.get(best_key, best_key)} ({best_score:.0f})"


def _component_total(scores: dict, keys: tuple[str, ...]) -> float | None:
    values = []
    for key in keys:
        comp = scores.get(key)
        if comp and comp.get("score") is not None:
            values.append(float(comp["score"]))
    return round(sum(values), 1) if values else None


def full_universe_dataframe(tickers: list[dict]) -> pd.DataFrame:
    """Full scan table with summary, component scores, and fundamental metrics."""
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
            "top_signal": _top_signal(scores),
            "tech_score": _component_total(scores, TECHNICAL_KEYS),
            "fund_score": _component_total(scores, FUNDAMENTAL_KEYS),
            "filter_reason": fail_reason,
            "filter_label": FILTER_LABELS.get(fail_reason, fail_reason) if fail_reason else "",
        }
        for key, label in SCORE_LABELS.items():
            comp = scores.get(key)
            row[label] = round(comp.get("score", 0), 1) if comp else None
        rev_raw = scores.get("revenue", {}).get("raw", {})
        eps_raw = scores.get("eps", {}).get("raw", {})
        row["revenue_yoy_pct"] = rev_raw.get("revenue_yoy_pct")
        row["eps_growth_pct"] = eps_raw.get("eps_combined_pct")
        rows.append(row)
    return pd.DataFrame(rows).sort_values("final_score", ascending=False)


def score_heatmap_dataframe(tickers: list[dict], eligible_only: bool = True) -> pd.DataFrame:
    subset = [t for t in tickers if t.get("eligible")] if eligible_only else tickers
    rows = []
    for t in subset:
        scores = t.get("scores") or {}
        row = {"ticker": t["ticker"]}
        for key, label in SCORE_LABELS.items():
            comp = scores.get(key, {})
            row[label] = comp.get("score", 0)
        rows.append(row)
    return pd.DataFrame(rows)
