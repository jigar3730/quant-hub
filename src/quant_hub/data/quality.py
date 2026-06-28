"""Data-quality helpers for prices, fundamentals, and Lynch metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from quant_hub.config import MAX_REASONABLE_GROWTH, PRICE_SPIKE_RATIO

__all__ = [
    "OHLCVValidation",
    "growth_to_percent",
    "has_price_spike",
    "lynch_metrics_quality_summary",
    "max_bar_date",
    "normalize_debt_to_equity",
    "normalize_dividend_yield",
    "normalize_rate_decimal",
    "ohlcv_is_stale",
    "price_spike_ratio",
    "sanitize_growth_rate",
    "validate_ohlcv",
]


@dataclass(frozen=True)
class OHLCVValidation:
    ok: bool
    as_of: date | None
    issues: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "as_of": str(self.as_of) if self.as_of else None,
            "issues": list(self.issues),
        }


def sanitize_growth_rate(growth: float | None) -> float | None:
    """Drop YoY/CAGR values that are unreliable (bad base period or extreme spikes)."""
    if growth is None or pd.isna(growth):
        return None
    value = float(growth)
    if abs(value) > MAX_REASONABLE_GROWTH:
        return None
    return value


def normalize_rate_decimal(value: float | None) -> float | None:
    """
    Normalize a rate to decimal form (0.15 = 15%).

    Yahoo often returns decimals; some fields arrive as whole-number percents.
    """
    if value is None or pd.isna(value):
        return None
    v = float(value)
    if abs(v) > 1.5:
        return v / 100.0
    return v


def normalize_debt_to_equity(value: float | None) -> float | None:
    """
    Normalize debt/equity to a ratio (0.45 = 45% leverage).

    Yahoo ``debtToEquity`` is usually a whole-number percent (e.g. 45.5).
    Values already in ratio form (<= 5) are kept as-is.
    """
    if value is None or pd.isna(value):
        return None
    ratio = float(value)
    if ratio > 5.0:
        ratio /= 100.0
    return ratio


def normalize_dividend_yield(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    v = float(value)
    if v > 0.20:
        v /= 100.0
    return v


def growth_to_percent(growth: float | None) -> float | None:
    """Convert growth to whole-number percent for PEG (e.g. 0.20 -> 20)."""
    if growth is None or pd.isna(growth):
        return None
    g = float(growth)
    if abs(g) <= 1.5:
        return g * 100.0
    return g


def max_bar_date(df: pd.DataFrame | None) -> date | None:
    if df is None or df.empty or "Date" not in df.columns:
        return None
    ts = pd.to_datetime(df["Date"]).max()
    if pd.isna(ts):
        return None
    return ts.date()


def ohlcv_is_stale(df: pd.DataFrame | None, *, max_age_days: int) -> bool:
    as_of = max_bar_date(df)
    if as_of is None:
        return True
    return (date.today() - as_of) > timedelta(days=max_age_days)


def validate_ohlcv(
    df: pd.DataFrame | None,
    *,
    min_rows: int = 1,
    max_spike_ratio: float = PRICE_SPIKE_RATIO,
    max_staleness_days: int | None = None,
) -> OHLCVValidation:
    """Validate OHLCV frame before scoring."""
    issues: list[str] = []
    if df is None or df.empty:
        return OHLCVValidation(ok=False, as_of=None, issues=("empty",))

    missing = [c for c in ("Date", "Close") if c not in df.columns]
    if missing:
        return OHLCVValidation(ok=False, as_of=None, issues=(f"missing_columns:{','.join(missing)}",))

    if len(df) < min_rows:
        issues.append(f"insufficient_rows:{len(df)}<{min_rows}")

    if df["Close"].isna().iloc[-1]:
        issues.append("nan_close")

    if has_price_spike(df, max_ratio=max_spike_ratio):
        ratio = price_spike_ratio(df)
        issues.append(f"price_spike:{ratio:.2f}" if ratio else "price_spike")

    as_of = max_bar_date(df)
    if max_staleness_days is not None and ohlcv_is_stale(df, max_age_days=max_staleness_days):
        issues.append(f"stale:{as_of}")

    return OHLCVValidation(ok=len(issues) == 0, as_of=as_of, issues=tuple(issues))


def price_spike_ratio(df: pd.DataFrame) -> float | None:
    """Latest close divided by the prior 20-session median close."""
    close = df["Close"]
    if len(close) < 21:
        return None
    last = float(close.iloc[-1])
    median = float(close.tail(20).median())
    if median <= 0:
        return None
    return last / median


def has_price_spike(df: pd.DataFrame, *, max_ratio: float = PRICE_SPIKE_RATIO) -> bool:
    """True when the latest close deviates sharply from recent history."""
    ratio = price_spike_ratio(df)
    if ratio is None:
        return False
    return ratio > max_ratio or ratio < (1 / max_ratio)


def lynch_metrics_quality_summary(metrics_list: list[dict]) -> dict[str, Any]:
    """Aggregate data-quality metrics for Lynch scan metadata."""
    n = len(metrics_list)
    if n == 0:
        return {"tickers": 0}

    def _missing(field: str) -> int:
        return sum(1 for m in metrics_list if m.get(field) is None and not m.get("error"))

    fetch_errors = sum(1 for m in metrics_list if m.get("error"))
    ok = n - fetch_errors

    return {
        "tickers": n,
        "fetch_errors": fetch_errors,
        "fetch_ok_pct": round(ok / n * 100, 1) if n else 0.0,
        "missing_pe": _missing("pe_ratio"),
        "missing_peg": _missing("peg_ratio"),
        "missing_roe": _missing("return_on_equity"),
        "missing_institutional": _missing("institutional_ownership"),
        "missing_insider": sum(
            1
            for m in metrics_list
            if m.get("insider_purchases_6m") is None
            and m.get("shares_outstanding_change_yoy") is None
            and not m.get("error")
        ),
        "data_complete_pct": round(
            sum(1 for m in metrics_list if m.get("data_quality", {}).get("complete")) / n * 100,
            1,
        )
        if n
        else 0.0,
    }
