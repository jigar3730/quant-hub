"""Load Peter Lynch scan reports for the dashboard."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quant_hub.config import DEFAULT_LYNCH_JSON, HISTORY_DIR
from quant_hub.dashboard.viz.display import format_display_value

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
        options[str(DEFAULT_LYNCH_JSON)] = "Latest (data/output)"
    for p in sorted(HISTORY_DIR.glob("*/lynch_scan_report.json"), reverse=True):
        options[str(p)] = f"Archive {p.parent.name}"
    return options


def lynch_tickers_to_dataframe(tickers: list[dict]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        cats = t.get("categories") or []
        rows.append(
            {
                "ticker": t["ticker"],
                "company_name": t.get("company_name"),
                "sector": t.get("sector"),
                "passed": bool(t.get("passed")),
                "categories": ", ".join(cats) if cats else "base",
                "lynch_score": t.get("lynch_score", 0),
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
                "check": check.get("rule") or check.get("label") or check.get("id", ""),
                "passed": bool(check.get("passed")),
                "value": format_display_value(check.get("value")),
                "threshold": format_display_value(check.get("threshold")),
                "detail": check.get("detail", ""),
            }
        )
    return pd.DataFrame(rows)
