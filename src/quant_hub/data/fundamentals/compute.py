"""Fundamental growth calculations with turnaround / TTM / fallback support."""

from __future__ import annotations

import pandas as pd

from quant_hub.config import MAX_REASONABLE_GROWTH
from quant_hub.data.fundamentals.types import MetricStatus
from quant_hub.data.fundamentals_helpers import cagr, quarterly_series

# Turnaround from loss to profit maps to this synthetic YoY for scoring tiers.
TURNAROUND_GROWTH = 0.50


def apply_growth_cap(value: float | None) -> tuple[float | None, MetricStatus]:
    if value is None or pd.isna(value):
        return None, "MISSING"
    v = float(value)
    if v > MAX_REASONABLE_GROWTH:
        return MAX_REASONABLE_GROWTH, "CAPPED"
    if v < -MAX_REASONABLE_GROWTH:
        return -MAX_REASONABLE_GROWTH, "CAPPED"
    return v, "OK"


def yoy_quarterly(series: pd.Series, quarters_back: int = 4) -> tuple[float | None, MetricStatus]:
    """YoY on single quarter points; handles negative / turnaround bases."""
    if len(series) <= quarters_back:
        return None, "MISSING"
    recent = float(series.iloc[-1])
    prior = float(series.iloc[-1 - quarters_back])
    if pd.isna(recent) or pd.isna(prior):
        return None, "MISSING"

    if prior > 0:
        return apply_growth_cap((recent / prior) - 1)

    if prior < 0 < recent:
        return apply_growth_cap(TURNAROUND_GROWTH)

    if prior < 0 and recent < 0:
        # Loss narrowing (less negative = improvement)
        return apply_growth_cap((recent - prior) / abs(prior))

    if prior == 0:
        if recent > 0:
            return apply_growth_cap(TURNAROUND_GROWTH)
        return None, "NOT_APPLICABLE"

    return None, "NOT_APPLICABLE"


def ttm_yoy(series: pd.Series) -> tuple[float | None, MetricStatus]:
    """Trailing-four-quarters YoY — stable for lumpy EPS."""
    if len(series) < 8:
        return None, "MISSING"
    ttm_now = float(series.iloc[-4:].sum())
    ttm_prior = float(series.iloc[-8:-4].sum())
    if pd.isna(ttm_now) or pd.isna(ttm_prior):
        return None, "MISSING"

    if ttm_prior > 0:
        return apply_growth_cap((ttm_now / ttm_prior) - 1)

    if ttm_prior < 0 < ttm_now:
        return apply_growth_cap(TURNAROUND_GROWTH)

    if ttm_prior < 0 and ttm_now < 0:
        return apply_growth_cap((ttm_now - ttm_prior) / abs(ttm_prior))

    if ttm_prior == 0:
        if ttm_now > 0:
            return apply_growth_cap(TURNAROUND_GROWTH)
        return None, "NOT_APPLICABLE"

    return None, "NOT_APPLICABLE"


def revenue_yoy_blended(series: pd.Series) -> tuple[float | None, MetricStatus, str]:
    if series.empty:
        return None, "MISSING", ""
    if len(series) <= 4:
        val, status = yoy_quarterly(series)
        return val, status, "single_quarter_yoy"

    q1, s1 = yoy_quarterly(series)
    recent = float(series.iloc[-1])
    prior = float(series.iloc[-5])
    if prior > 0 and not pd.isna(recent):
        q2 = (float(series.iloc[-2]) / float(series.iloc[-6]) - 1) if len(series) > 5 else None
        if q1 is not None and q2 is not None:
            blended, status = apply_growth_cap((q1 + q2) / 2)
            return blended, status, "two_quarter_yoy_avg"
    val, status = yoy_quarterly(series)
    return val, status, "single_quarter_yoy"


def eps_combined_growth(
    eps: pd.Series,
    *,
    operating_income: pd.Series | None = None,
    net_income: pd.Series | None = None,
) -> tuple[float | None, MetricStatus, float | None, float | None, str]:
    """
    Returns (combined, combined_status, eps_yoy, eps_cagr_3y, source).
    Priority: TTM diluted EPS → quarterly YoY → operating income TTM → net income TTM.
    """
    source = ""
    eps_yoy: float | None = None
    eps_yoy_status: MetricStatus = "MISSING"

    if not eps.empty:
        if len(eps) >= 8:
            eps_yoy, eps_yoy_status = ttm_yoy(eps)
            source = "diluted_eps_ttm"
        else:
            eps_yoy, eps_yoy_status = yoy_quarterly(eps)
            source = "diluted_eps_quarter"

    eps_cagr: float | None = None
    if not eps.empty:
        cagr_raw = cagr(eps, years=3.0)
        if cagr_raw is not None:
            eps_cagr, _ = apply_growth_cap(cagr_raw)

    if eps_yoy is not None:
        if eps_cagr is not None:
            combined, comb_status = apply_growth_cap(0.7 * eps_yoy + 0.3 * eps_cagr)
        else:
            combined, comb_status = eps_yoy, eps_yoy_status
        return combined, comb_status, eps_yoy, eps_cagr, source

    for fallback_series, label in (
        (operating_income, "operating_income_ttm"),
        (net_income, "net_income_ttm"),
    ):
        if fallback_series is None or fallback_series.empty:
            continue
        val, status = (
            ttm_yoy(fallback_series)
            if len(fallback_series) >= 8
            else yoy_quarterly(fallback_series)
        )
        if val is not None:
            return val, status, None, None, label

    if eps.empty:
        return None, "MISSING", None, None, ""
    return None, eps_yoy_status if eps_yoy_status != "OK" else "NOT_APPLICABLE", None, eps_cagr, source


def extract_income_series(income: pd.DataFrame) -> dict[str, pd.Series]:
    if income is None or income.empty:
        return {}
    out: dict[str, pd.Series] = {}
    for field, candidates in (
        ("revenue", ("Total Revenue", "Revenue")),
        ("eps", ("Diluted EPS", "Basic EPS")),
        ("operating_income", ("Operating Income", "Total Operating Income As Reported")),
        ("net_income", ("Net Income", "Net Income Common Stockholders")),
    ):
        for name in candidates:
            series = quarterly_series(income, name)
            if not series.empty:
                out[field] = series
                break
    return out
