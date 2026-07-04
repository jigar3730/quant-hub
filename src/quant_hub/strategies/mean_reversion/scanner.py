"""Daily mean reversion scanner — rubric v2.2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from quant_hub.indicators import atr, bollinger_bands, ema, rsi
from quant_hub.scoring.relative_strength import compute_rs_market_ratio
from quant_hub.strategies.mean_reversion.constants import (
    FILTER_LABELS,
    SETUP_LONG,
    TIER_FILTERED,
    TIER_HIGH_CONVICTION,
    TIER_WATCHLIST,
)
from quant_hub.strategies.mean_reversion.scoring import MeanReversionScoreResult, score_mean_reversion
from quant_hub.strategies.mean_reversion.trade_plan import build_trade_card, build_watchlist_row


@dataclass
class MeanReversionAnalysis:
    ticker: str
    close: float
    ema500: float
    bb_upper: float
    bb_mid: float
    bb_lower: float
    rsi: float
    atr: float
    rs_ratio: float | None = None
    rs_percentile: float | None = None
    fail_reason: str | None = None
    score_result: MeanReversionScoreResult | None = None
    bars_evaluated: int = 0


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["EMA500"] = ema(out["Close"], 500)
    upper, mid, lower = bollinger_bands(out["Close"], 20)
    out["BB_Upper"] = upper
    out["BB_Mid"] = mid
    out["BB_Lower"] = lower
    out["RSI"] = rsi(out["Close"], 14)
    out["ATR"] = atr(out, 14)
    return out.dropna()


def analyze_ticker(
    df: pd.DataFrame,
    ticker: str,
    *,
    spy_df: pd.DataFrame | None = None,
    rs_percentile: float | None = None,
    min_bars: int = 520,
) -> MeanReversionAnalysis:
    if len(df) < min_bars:
        return MeanReversionAnalysis(
            ticker=ticker,
            close=0.0,
            ema500=0.0,
            bb_upper=0.0,
            bb_mid=0.0,
            bb_lower=0.0,
            rsi=0.0,
            atr=0.0,
            fail_reason="insufficient_data",
        )

    try:
        enriched = add_indicators(df)
    except Exception:
        return MeanReversionAnalysis(
            ticker=ticker,
            close=0.0,
            ema500=0.0,
            bb_upper=0.0,
            bb_mid=0.0,
            bb_lower=0.0,
            rsi=0.0,
            atr=0.0,
            fail_reason="scan_error",
        )

    if enriched.empty:
        return MeanReversionAnalysis(
            ticker=ticker,
            close=0.0,
            ema500=0.0,
            bb_upper=0.0,
            bb_mid=0.0,
            bb_lower=0.0,
            rsi=0.0,
            atr=0.0,
            fail_reason="insufficient_data",
        )

    latest = enriched.iloc[-1]
    rs_ratio = None
    if spy_df is not None and not spy_df.empty:
        rs_ratio = compute_rs_market_ratio(df, spy_df)

    analysis = MeanReversionAnalysis(
        ticker=ticker,
        close=float(latest["Close"]),
        ema500=float(latest["EMA500"]),
        bb_upper=float(latest["BB_Upper"]),
        bb_mid=float(latest["BB_Mid"]),
        bb_lower=float(latest["BB_Lower"]),
        rsi=float(latest["RSI"]),
        atr=float(latest["ATR"]),
        rs_ratio=rs_ratio,
        rs_percentile=rs_percentile,
        bars_evaluated=len(enriched),
    )
    analysis.score_result = score_mean_reversion(enriched, rs_percentile=rs_percentile)
    return analysis


def _tier_reason(analysis: MeanReversionAnalysis, score: MeanReversionScoreResult) -> str:
    if analysis.fail_reason:
        return FILTER_LABELS.get(analysis.fail_reason, analysis.fail_reason)
    if score.tier == TIER_HIGH_CONVICTION:
        return score.signal
    if score.tier == TIER_WATCHLIST:
        row = build_watchlist_row(analysis, score)
        return row.get("notes") or score.signal
    return score.signal


def analysis_to_report(
    analysis: MeanReversionAnalysis,
    df: pd.DataFrame,
    *,
    scan_date=None,
) -> dict:
    score = analysis.score_result
    if score is None:
        score = MeanReversionScoreResult(
            total_score=0.0,
            scored_side="long",
            setup_type=SETUP_LONG,
            signal="No Trade",
            tier=TIER_FILTERED,
            rule_breakdown=[],
            long_score=0.0,
            short_score=0.0,
        )

    passed = analysis.fail_reason is None and score.tier != TIER_FILTERED
    tier = score.tier if analysis.fail_reason is None else TIER_FILTERED
    tier_reason = _tier_reason(analysis, score)

    setup_detail: dict[str, Any] = {
        "close": analysis.close,
        "ema500": analysis.ema500,
        "bb_upper": analysis.bb_upper,
        "bb_mid": analysis.bb_mid,
        "bb_lower": analysis.bb_lower,
        "rsi": analysis.rsi,
        "atr": analysis.atr,
        "bars_evaluated": analysis.bars_evaluated,
        "bias": score.scored_side,
        "signal": score.signal,
        "long_score": score.long_score,
        "short_score": score.short_score,
        "rule_breakdown": score.rule_breakdown,
        "rs_ratio": analysis.rs_ratio,
        "rs_percentile": analysis.rs_percentile,
        "notes": tier_reason,
    }

    if tier == TIER_HIGH_CONVICTION and analysis.fail_reason is None:
        setup_detail["trade_plan"] = build_trade_card(
            analysis, score, df, scan_date=scan_date
        )
    elif tier == TIER_WATCHLIST and analysis.fail_reason is None:
        setup_detail["watchlist"] = build_watchlist_row(analysis, score)

    return {
        "ticker": analysis.ticker,
        "eligible": passed,
        "tier": tier,
        "sector_etf": None,
        "tier_reason": tier_reason,
        "summary": {
            "mean_reversion_score": score.total_score,
            "final_adjusted_score": score.total_score,
            "normalized_score": score.total_score,
            "raw_score": score.total_score,
            "signal": score.signal,
            "setup_type": score.setup_type,
            "long_score": score.long_score,
            "short_score": score.short_score,
        },
        "scores": {
            item["rule"]: {
                "score": item["score"],
                "max": item["max"],
                "passed": item["passed"],
                "meaning": item["label"],
                "detail": item.get("detail", ""),
            }
            for item in score.rule_breakdown
        },
        "eligibility": {
            "passed": passed,
            "fail_reason": analysis.fail_reason,
            "checks": [],
        },
        "setup_detail": setup_detail,
    }
