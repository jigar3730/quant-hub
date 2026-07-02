"""Load Peter Lynch scan reports for the dashboard."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quant_hub.config import HISTORY_DIR, PRIMARY_INDEX_UNIVERSE, scan_output_paths
from quant_hub.dashboard.viz.display import format_display_value

DEFAULT_LYNCH_JSON = scan_output_paths("lynch", PRIMARY_INDEX_UNIVERSE)["json"]

CATEGORY_COLORS = {
    "fast_grower": "#22c55e",
    "stalwart": "#3b82f6",
    "asset_play": "#a855f7",
    "base": "#94a3b8",
}


def load_lynch_report(path: Path | str = DEFAULT_LYNCH_JSON) -> dict:
    path = Path(path)
    with path.open() as f:
        return json.load(f)


def list_lynch_report_paths() -> dict[str, str]:
    """Map path string -> sidebar label (latest first)."""
    options: dict[str, str] = {}
    if DEFAULT_LYNCH_JSON.exists():
        options[str(DEFAULT_LYNCH_JSON)] = f"Latest ({PRIMARY_INDEX_UNIVERSE})"
    for p in sorted(HISTORY_DIR.glob("*/lynch_scan_report.json"), reverse=True):
        options[str(p)] = f"Archive {p.parent.name}"
    return options


def _lynch_score_display(value) -> float | None:
    if value is None:
        return None
    return float(value)


def lynch_tickers_to_dataframe(tickers: list[dict]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        cats = t.get("categories") or []
        score = t.get("lynch_score")
        rows.append(
            {
                "ticker": t["ticker"],
                "company_name": t.get("company_name"),
                "sector": t.get("sector"),
                "passed": bool(t.get("passed")),
                "categories": ", ".join(cats) if cats else "base",
                "lynch_score": _lynch_score_display(score),
                "data_status": "unavailable" if (t.get("metrics") or {}).get("error") else "ok",
                "pe_ratio": t.get("pe_ratio"),
                "peg_ratio": t.get("peg_ratio"),
                "eps_growth_5y_pct": t.get("eps_growth_5y_pct"),
                "debt_to_equity": t.get("debt_to_equity"),
                "institutional_pct": t.get("institutional_pct"),
                "analyst_count": t.get("analyst_count"),
                "market_cap": t.get("market_cap"),
                "dividend_yield": t.get("dividend_yield"),
                "price_to_book": t.get("price_to_book"),
                "tier_reason": t.get("tier_reason", ""),
                "fail_reason": t.get("fail_reason", ""),
            }
        )
    return pd.DataFrame(rows)


def lynch_checks_dataframe(ticker: dict) -> pd.DataFrame:
    rows = []
    for check in ticker.get("checks") or []:
        rows.append(
            {
                "check": check.get("label") or check.get("rule") or check.get("id", ""),
                "passed": bool(check.get("passed")),
                "value": format_display_value(check.get("plain_value", check.get("value"))),
                "threshold": format_display_value(check.get("threshold")),
                "why": check.get("why_it_matters") or check.get("detail", ""),
                "result": check.get("result_text", ""),
            }
        )
    return pd.DataFrame(rows)
