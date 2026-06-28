"""Swing dashboard filter helpers and dataframe builders."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_hub.dashboard.viz.labels import tier_friendly
from quant_hub.strategies.swing.scanner import SWING_FILTER_LABELS


@dataclass(frozen=True)
class SwingFilters:
    setup_type: str = "All"
    min_rsi: float = 0.0
    search: str = ""


def _fail_label(ticker: dict) -> str:
    fail = (ticker.get("eligibility") or {}).get("fail_reason") or ""
    return ticker.get("tier_reason") or SWING_FILTER_LABELS.get(fail, fail)


def _swing_score(t: dict) -> float | None:
    detail = t.get("setup_detail") or {}
    summary = t.get("summary") or {}
    if detail.get("swing_score") is not None:
        return float(detail["swing_score"])
    if summary.get("swing_score") is not None:
        return float(summary["swing_score"])
    passed = detail.get("checks_passed")
    total = detail.get("checks_total") or 5
    if passed is not None:
        return round(float(passed) / float(total) * 100, 1)
    if t.get("tier") in ("SETUP_LONG", "SETUP_SHORT"):
        return 100.0
    return None


def _indicator_row(t: dict) -> dict:
    detail = t.get("setup_detail") or {}
    tier = t.get("tier", "filtered")
    checks_passed = detail.get("checks_passed")
    checks_total = detail.get("checks_total")
    checks_str = (
        f"{checks_passed}/{checks_total}"
        if checks_passed is not None and checks_total
        else "—"
    )
    score = _swing_score(t)
    return {
        "ticker": t["ticker"],
        "status": tier_friendly(tier) if tier in ("SETUP_LONG", "SETUP_SHORT") else "No setup",
        "setup_type": tier if tier in ("SETUP_LONG", "SETUP_SHORT") else "—",
        "score": score,
        "quality": detail.get("quality_label") or "—",
        "close": detail.get("close"),
        "rsi": detail.get("rsi"),
        "ema20": detail.get("ema20"),
        "ema50": detail.get("ema50"),
        "atr": detail.get("atr"),
        "macd_hist": detail.get("macd_hist"),
        "checks": checks_str,
        "reason": _fail_label(t),
    }


def swing_setups_dataframe(tickers: list[dict]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        if t.get("tier") not in ("SETUP_LONG", "SETUP_SHORT"):
            continue
        row = _indicator_row(t)
        row["setup_type"] = tier_friendly(t.get("tier", ""))
        row["notes"] = row.pop("reason")
        rows.append(row)
    if not rows:
        return pd.DataFrame(
            columns=[
                "ticker",
                "setup_type",
                "score",
                "quality",
                "close",
                "rsi",
                "ema20",
                "ema50",
                "atr",
                "macd_hist",
                "checks",
                "notes",
            ]
        )
    return pd.DataFrame(rows).sort_values("score", ascending=False)


def swing_universe_dataframe(tickers: list[dict]) -> pd.DataFrame:
    rows = [_indicator_row(t) for t in tickers]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["status", "ticker"])


def apply_swing_filters(df: pd.DataFrame, filters: SwingFilters) -> pd.DataFrame:
    result = df.copy()
    if filters.setup_type != "All":
        if filters.setup_type == "SETUP_LONG":
            result = result[result["setup_type"].isin(["SETUP_LONG", "Long setup"])]
        elif filters.setup_type == "SETUP_SHORT":
            result = result[result["setup_type"].isin(["SETUP_SHORT", "Short setup"])]
        else:
            friendly = tier_friendly(filters.setup_type)
            result = result[result["setup_type"] == friendly]
    if filters.min_rsi > 0 and "rsi" in result.columns:
        result = result[result["rsi"].fillna(0) >= filters.min_rsi]
    if filters.search:
        result = result[result["ticker"].str.contains(filters.search, na=False)]
    return result
