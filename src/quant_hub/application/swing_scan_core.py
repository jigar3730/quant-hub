"""Shared swing scan loop used by live scans and historical backfill."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from quant_hub.config import SWING_MIN_BARS
from quant_hub.data.quality import validate_ohlcv
from quant_hub.strategies.swing.scanner import (
    SwingSetup,
    add_indicators,
    analysis_to_report,
    analyze_swing,
)
from quant_hub.strategies.swing.scoring import score_swing_quality

logger = logging.getLogger(__name__)


def data_error_report(ticker: str, reason: str) -> dict:
    from quant_hub.strategies.swing.scanner import SWING_FILTER_LABELS

    label = SWING_FILTER_LABELS.get(reason, reason.replace("_", " ").title())
    return {
        "ticker": ticker,
        "eligible": False,
        "tier": "filtered",
        "sector_etf": None,
        "tier_reason": label,
        "summary": {},
        "scores": {},
        "eligibility": {"passed": False, "fail_reason": reason, "checks": []},
        "setup_detail": {"notes": label},
        "swing_checks": [],
    }


def scan_universe_weekly(
    universe: list[str],
    price_map: dict[str, pd.DataFrame],
    spy_df: pd.DataFrame | None,
    *,
    min_bars: int = SWING_MIN_BARS,
    skip_staleness: bool = False,
) -> tuple[list[SwingSetup], list[dict[str, Any]], dict[str, int]]:
    """
    Run swing analysis for every ticker in `universe`.

    Returns (setups, ticker_reports, rejection_counts).
    """
    rejection_counts: dict[str, int] = {}
    setups: list[SwingSetup] = []
    ticker_reports: list[dict[str, Any]] = []
    pending: list[tuple[str, pd.DataFrame, Any]] = []

    max_staleness = None if skip_staleness else 14

    for ticker in universe:
        df = price_map.get(ticker)
        if df is None or df.empty:
            reason = "no_price_data"
            ticker_reports.append(data_error_report(ticker, reason))
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            continue
        validation = validate_ohlcv(
            df,
            min_rows=min_bars,
            max_staleness_days=max_staleness,
        )
        if not validation.ok:
            reason = validation.issues[0] if validation.issues else "invalid_ohlcv"
            ticker_reports.append(data_error_report(ticker, reason))
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            continue
        if len(df) < min_bars:
            reason = "insufficient_data"
            ticker_reports.append(data_error_report(ticker, reason))
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            continue
        try:
            analysis = analyze_swing(
                df,
                ticker,
                min_bars=min_bars,
                spy_df=spy_df,
            )
            pending.append((ticker, df, analysis))
        except Exception:
            logger.exception("Swing scan failed for %s", ticker)
            reason = "scan_error"
            ticker_reports.append(data_error_report(ticker, reason))
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
        if len(enriched) >= 3:
            analysis.score_result = score_swing_quality(analysis, enriched)
        ticker_reports.append(analysis_to_report(analysis))
        if analysis.setup:
            setups.append(analysis.setup)
        elif analysis.fail_reason:
            rejection_counts[analysis.fail_reason] = (
                rejection_counts.get(analysis.fail_reason, 0) + 1
            )

    return setups, ticker_reports, rejection_counts
