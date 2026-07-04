"""Shared mean reversion scan loop."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd

from quant_hub.config import MEAN_REVERSION_MIN_BARS
from quant_hub.data.quality import validate_ohlcv
from quant_hub.strategies.mean_reversion.constants import (
    FILTER_LABELS,
    TIER_FILTERED,
    TIER_HIGH_CONVICTION,
    TIER_WATCHLIST,
)
from quant_hub.strategies.mean_reversion.scanner import (
    add_indicators,
    analysis_to_report,
    analyze_ticker,
)
from quant_hub.strategies.mean_reversion.scoring import score_mean_reversion

logger = logging.getLogger(__name__)


def data_error_report(ticker: str, reason: str) -> dict:
    label = FILTER_LABELS.get(reason, reason.replace("_", " ").title())
    return {
        "ticker": ticker,
        "eligible": False,
        "tier": TIER_FILTERED,
        "sector_etf": None,
        "tier_reason": label,
        "summary": {},
        "scores": {},
        "eligibility": {"passed": False, "fail_reason": reason, "checks": []},
        "setup_detail": {"notes": label},
    }


def scan_universe_daily(
    universe: list[str],
    price_map: dict[str, pd.DataFrame],
    spy_df: pd.DataFrame | None,
    *,
    min_bars: int = MEAN_REVERSION_MIN_BARS,
    skip_staleness: bool = False,
    scan_date: date | None = None,
) -> tuple[list[dict], list[dict], list[dict], dict[str, int]]:
    """
    Run mean reversion analysis for every ticker in `universe`.

    Returns (high_conviction, watchlist, all_reports, rejection_counts).
    """
    rejection_counts: dict[str, int] = {}
    high_conviction: list[dict] = []
    watchlist: list[dict] = []
    all_reports: list[dict[str, Any]] = []
    pending: list[tuple[str, pd.DataFrame, Any]] = []

    max_staleness = None if skip_staleness else 5

    for ticker in universe:
        df = price_map.get(ticker)
        if df is None or df.empty:
            reason = "no_price_data"
            all_reports.append(data_error_report(ticker, reason))
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            continue
        validation = validate_ohlcv(
            df,
            min_rows=min_bars,
            max_staleness_days=max_staleness,
        )
        if not validation.ok:
            reason = validation.issues[0] if validation.issues else "invalid_ohlcv"
            all_reports.append(data_error_report(ticker, reason))
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            continue
        if len(df) < min_bars:
            reason = "insufficient_data"
            all_reports.append(data_error_report(ticker, reason))
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            continue
        try:
            analysis = analyze_ticker(
                df,
                ticker,
                min_bars=min_bars,
                spy_df=spy_df,
            )
            pending.append((ticker, df, analysis))
        except Exception:
            logger.exception("Mean reversion scan failed for %s", ticker)
            reason = "scan_error"
            all_reports.append(data_error_report(ticker, reason))
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

    rs_ratios = {
        item[2].ticker: item[2].rs_ratio for item in pending if item[2].rs_ratio is not None
    }
    if len(rs_ratios) >= 2:
        rs_pct = pd.Series(rs_ratios, dtype=float).rank(pct=True)
    else:
        rs_pct = pd.Series(dtype=float)

    for ticker, df, analysis in pending:
        if ticker in rs_pct.index:
            analysis.rs_percentile = float(rs_pct[ticker])
        enriched = add_indicators(df)
        if not enriched.empty:
            analysis.score_result = score_mean_reversion(
                enriched, rs_percentile=analysis.rs_percentile
            )
        report = analysis_to_report(analysis, df, scan_date=scan_date)
        all_reports.append(report)

        if analysis.fail_reason:
            rejection_counts[analysis.fail_reason] = (
                rejection_counts.get(analysis.fail_reason, 0) + 1
            )
            continue

        tier = report.get("tier")
        if tier == TIER_HIGH_CONVICTION:
            high_conviction.append(report)
        elif tier == TIER_WATCHLIST:
            watchlist.append(report)
        else:
            rejection_counts[TIER_FILTERED] = rejection_counts.get(TIER_FILTERED, 0) + 1

    return high_conviction, watchlist, all_reports, rejection_counts
