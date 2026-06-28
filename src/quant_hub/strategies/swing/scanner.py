"""Weekly swing setup scanner — ported from finance-vibe swing_scanner.py."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from quant_hub.indicators import atr, ema, macd_histogram, rsi

SWING_FILTER_LABELS = {
    "no_setup": "No long/short setup matched — review rule checklist",
    "insufficient_data": "Fewer than 60 weekly bars after indicators",
    "no_price_data": "No weekly OHLCV data",
    "invalid_ohlcv": "OHLCV failed validation",
    "scan_error": "Scanner error during evaluation",
    "stale_ohlcv": "Weekly bars are stale",
    "missing_columns": "OHLCV missing required columns",
}


@dataclass(frozen=True)
class SwingSetup:
    ticker: str
    setup_type: str  # SETUP_LONG | SETUP_SHORT
    close: float
    ema20: float
    ema50: float
    rsi: float
    atr: float
    notes: str


@dataclass
class SwingCheck:
    rule: str
    label: str
    passed: bool
    value: Any
    threshold: str
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "label": self.label,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "detail": self.detail,
        }


@dataclass
class SwingAnalysis:
    ticker: str
    setup: SwingSetup | None
    fail_reason: str | None
    close: float | None = None
    ema20: float | None = None
    ema50: float | None = None
    rsi: float | None = None
    atr: float | None = None
    macd_hist: float | None = None
    macd_hist_prev: float | None = None
    candidate: str = "neutral"  # long | short | neutral
    long_checks: list[SwingCheck] = field(default_factory=list)
    short_checks: list[SwingCheck] = field(default_factory=list)
    bars_evaluated: int = 0
    score_result: Any = None

    @property
    def active_checks(self) -> list[SwingCheck]:
        return self.long_checks if self.candidate == "long" else self.short_checks

    @property
    def checks_passed(self) -> int:
        return sum(1 for c in self.active_checks if c.passed)

    @property
    def checks_total(self) -> int:
        return len(self.active_checks)

    def setup_checks(self) -> list[SwingCheck]:
        if self.setup:
            return self.long_checks if self.setup.setup_type == "SETUP_LONG" else self.short_checks
        return self.active_checks


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["EMA20"] = ema(out["Close"], 20)
    out["EMA50"] = ema(out["Close"], 50)
    out["MACD_Hist"] = macd_histogram(out["Close"])
    out["RSI"] = rsi(out["Close"], 14)
    out["ATR"] = atr(out, 14)
    return out.dropna()


def momentum_ready_long(df: pd.DataFrame) -> bool:
    h = df["MACD_Hist"].tail(3)
    if len(h) < 3:
        return False
    is_rising = h.iloc[-1] > h.iloc[-2]
    was_rising = h.iloc[-2] > h.iloc[-3]
    hist_std = df["MACD_Hist"].rolling(20).std().iloc[-1]
    not_overextended = h.iloc[-1] < hist_std * 2
    return bool(is_rising and was_rising and not_overextended)


def momentum_ready_short(df: pd.DataFrame) -> bool:
    h = df["MACD_Hist"].tail(3)
    if len(h) < 3:
        return False
    is_falling = h.iloc[-1] < h.iloc[-2]
    was_falling = h.iloc[-2] < h.iloc[-3]
    hist_std = df["MACD_Hist"].rolling(20).std().iloc[-1]
    not_overextended = h.iloc[-1] > -hist_std * 2
    return bool(is_falling and was_falling and not_overextended)


def _check(
    rule: str,
    label: str,
    passed: bool,
    *,
    value: Any,
    threshold: str,
    detail: str = "",
) -> SwingCheck:
    return SwingCheck(
        rule=rule,
        label=label,
        passed=passed,
        value=value,
        threshold=threshold,
        detail=detail,
    )


def build_long_checks(df: pd.DataFrame, *, rsi_min: float = 45) -> list[SwingCheck]:
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["Close"])
    ema20 = float(latest["EMA20"])
    ema50 = float(latest["EMA50"])
    rsi_val = float(latest["RSI"])
    ema50_prev = float(prev["EMA50"])
    pullback_lo = ema20
    pullback_hi = ema20 * 1.02

    return [
        _check(
            "long_trend",
            "Uptrend (EMA20 > EMA50)",
            ema20 > ema50,
            value={"ema20": round(ema20, 2), "ema50": round(ema50, 2)},
            threshold="EMA20 > EMA50",
        ),
        _check(
            "long_ema50_rising",
            "EMA50 rising",
            ema50 > ema50_prev,
            value={"ema50": round(ema50, 2), "ema50_prev": round(ema50_prev, 2)},
            threshold="EMA50 > prior week",
        ),
        _check(
            "long_pullback_zone",
            "Pullback into 20 EMA",
            pullback_lo <= close <= pullback_hi,
            value={"close": round(close, 2), "zone": f"{pullback_lo:.2f}–{pullback_hi:.2f}"},
            threshold="Close within EMA20 to EMA20×1.02",
        ),
        _check(
            "long_rsi_band",
            "RSI in long band",
            rsi_min <= rsi_val <= 60,
            value=round(rsi_val, 1),
            threshold=f"{rsi_min:.0f} ≤ RSI ≤ 60",
        ),
        _check(
            "long_macd_momentum",
            "MACD histogram momentum",
            momentum_ready_long(df),
            value={
                "macd_hist": round(float(latest["MACD_Hist"]), 4),
                "macd_hist_prev": round(float(prev["MACD_Hist"]), 4),
            },
            threshold="Rising 2 weeks, not overextended vs 20w std",
        ),
    ]


def build_short_checks(df: pd.DataFrame) -> list[SwingCheck]:
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["Close"])
    ema20 = float(latest["EMA20"])
    ema50 = float(latest["EMA50"])
    rsi_val = float(latest["RSI"])
    ema50_prev = float(prev["EMA50"])
    pullback_lo = ema20 * 0.98
    pullback_hi = ema20

    return [
        _check(
            "short_trend",
            "Downtrend (EMA20 < EMA50)",
            ema20 < ema50,
            value={"ema20": round(ema20, 2), "ema50": round(ema50, 2)},
            threshold="EMA20 < EMA50",
        ),
        _check(
            "short_ema50_falling",
            "EMA50 falling",
            ema50 < ema50_prev,
            value={"ema50": round(ema50, 2), "ema50_prev": round(ema50_prev, 2)},
            threshold="EMA50 < prior week",
        ),
        _check(
            "short_pullback_zone",
            "Pullback into 20 EMA",
            pullback_lo <= close <= pullback_hi,
            value={"close": round(close, 2), "zone": f"{pullback_lo:.2f}–{pullback_hi:.2f}"},
            threshold="Close within EMA20×0.98 to EMA20",
        ),
        _check(
            "short_rsi_band",
            "RSI in short band",
            50 <= rsi_val <= 65,
            value=round(rsi_val, 1),
            threshold="50 ≤ RSI ≤ 65",
        ),
        _check(
            "short_macd_momentum",
            "MACD histogram momentum",
            momentum_ready_short(df),
            value={
                "macd_hist": round(float(latest["MACD_Hist"]), 4),
                "macd_hist_prev": round(float(prev["MACD_Hist"]), 4),
            },
            threshold="Falling 2 weeks, not overextended vs 20w std",
        ),
    ]


def _pick_candidate(long_checks: list[SwingCheck], short_checks: list[SwingCheck]) -> str:
    long_pass = sum(1 for c in long_checks if c.passed)
    short_pass = sum(1 for c in short_checks if c.passed)
    if long_pass >= short_pass and long_checks[0].passed:
        return "long"
    if short_pass > long_pass and short_checks[0].passed:
        return "short"
    if long_pass >= short_pass:
        return "long"
    return "short"


def evaluate_setup(df: pd.DataFrame, *, rsi_min_long: float = 45) -> dict | None:
    """Return setup dict or None. Logic matches finance-vibe weekly profile."""
    long_checks = build_long_checks(df, rsi_min=rsi_min_long)
    if all(c.passed for c in long_checks):
        return {"Setup Type": "SETUP_LONG", "Notes": "Pullback into 20EMA"}

    short_checks = build_short_checks(df)
    if all(c.passed for c in short_checks):
        return {"Setup Type": "SETUP_SHORT", "Notes": "Pullback into 20EMA"}

    return None


def analyze_swing(
    df: pd.DataFrame,
    ticker: str,
    *,
    min_bars: int = 60,
    rsi_min_long: float = 45,
) -> SwingAnalysis:
    """Full weekly indicator snapshot and rule checklist for any ticker."""
    symbol = ticker.upper()
    if len(df) < min_bars:
        return SwingAnalysis(ticker=symbol, setup=None, fail_reason="insufficient_data")

    enriched = add_indicators(df)
    if len(enriched) < 3:
        return SwingAnalysis(
            ticker=symbol,
            setup=None,
            fail_reason="insufficient_data",
            bars_evaluated=len(enriched),
        )

    latest = enriched.iloc[-1]
    prev = enriched.iloc[-2]
    close = round(float(latest["Close"]), 2)
    ema20 = round(float(latest["EMA20"]), 2)
    ema50 = round(float(latest["EMA50"]), 2)
    rsi_val = round(float(latest["RSI"]), 2)
    atr_val = round(float(latest["ATR"]), 2)
    macd = round(float(latest["MACD_Hist"]), 4)
    macd_prev = round(float(prev["MACD_Hist"]), 4)

    long_checks = build_long_checks(enriched, rsi_min=rsi_min_long)
    short_checks = build_short_checks(enriched)
    candidate = _pick_candidate(long_checks, short_checks)

    setup_raw = evaluate_setup(enriched, rsi_min_long=rsi_min_long)
    setup = None
    fail_reason = "no_setup"
    if setup_raw:
        setup = SwingSetup(
            ticker=symbol,
            setup_type=setup_raw["Setup Type"],
            close=close,
            ema20=ema20,
            ema50=ema50,
            rsi=rsi_val,
            atr=atr_val,
            notes=setup_raw["Notes"],
        )
        fail_reason = None

    analysis = SwingAnalysis(
        ticker=symbol,
        setup=setup,
        fail_reason=fail_reason,
        close=close,
        ema20=ema20,
        ema50=ema50,
        rsi=rsi_val,
        atr=atr_val,
        macd_hist=macd,
        macd_hist_prev=macd_prev,
        candidate=candidate,
        long_checks=long_checks,
        short_checks=short_checks,
        bars_evaluated=len(enriched),
    )
    analysis.score_result = _score_swing_quality(
        analysis, enriched, rsi_min_long=rsi_min_long
    )
    return analysis


def _score_swing_quality(analysis: SwingAnalysis, df: pd.DataFrame, *, rsi_min_long: float):
    from quant_hub.strategies.swing.scoring import score_swing_quality

    return score_swing_quality(analysis, df, rsi_min_long=rsi_min_long)


def scan_ticker(df: pd.DataFrame, ticker: str, *, min_bars: int = 60) -> SwingSetup | None:
    return analyze_swing(df, ticker, min_bars=min_bars).setup


def analysis_to_report(analysis: SwingAnalysis) -> dict:
    """Serialize full swing evaluation for Postgres / dashboard."""
    setup = analysis.setup
    tier = setup.setup_type if setup else "filtered"
    passed = setup is not None
    fail_reason = analysis.fail_reason
    scored_checks = analysis.setup_checks()
    if analysis.score_result is not None:
        score = analysis.score_result
    else:
        from quant_hub.strategies.swing.scoring import score_swing_quality

        score = score_swing_quality(analysis, pd.DataFrame())

    swing_score = score.swing_score
    rule_breakdown = score.rule_breakdown
    penalties = score.penalties
    base_score = score.base_score
    penalty_total = score.penalty_total
    quality_label = score.quality_label
    scored_side = score.scored_side
    active = analysis.active_checks
    failed_rules = [c.label for c in active if not c.passed]

    if setup:
        tier_reason = setup.notes
    elif failed_rules:
        tier_reason = f"No setup: failed {', '.join(failed_rules[:3])}"
        if len(failed_rules) > 3:
            tier_reason += f" (+{len(failed_rules) - 3} more)"
    else:
        tier_reason = SWING_FILTER_LABELS.get(fail_reason or "no_setup", fail_reason or "No setup")

    checks = [c.as_dict() for c in analysis.long_checks + analysis.short_checks]
    eligibility_checks = [c.as_dict() for c in active]

    return {
        "ticker": analysis.ticker,
        "eligible": passed,
        "tier": tier,
        "sector_etf": None,
        "tier_reason": tier_reason,
        "summary": {
            "swing_score": swing_score,
            "final_adjusted_score": swing_score,
            "normalized_score": swing_score,
            "raw_score": swing_score,
            "rsi": analysis.rsi,
        },
        "scores": {
            **{
                item["rule"]: {
                    "score": item["score"],
                    "max": item["max"],
                    "passed": item["passed"],
                    "meaning": item["label"],
                }
                for item in rule_breakdown
            },
            "swing_total": {
                "score": swing_score,
                "max": 100.0,
                "meaning": "Setup quality (base − penalties, 0–100)",
            },
            "swing_base": {
                "score": base_score,
                "max": 100.0,
                "meaning": "Base score before penalties",
            },
            "ema20": {"score": analysis.ema20, "max": 0, "meaning": "20-week EMA (level)"},
            "ema50": {"score": analysis.ema50, "max": 0, "meaning": "50-week EMA (level)"},
            "rsi": {"score": analysis.rsi, "max": 100, "meaning": "14-period RSI (weekly)"},
            "atr": {"score": analysis.atr, "max": 0, "meaning": "14-period ATR (weekly)"},
            "macd_hist": {
                "score": analysis.macd_hist,
                "max": 0,
                "meaning": "MACD histogram (latest week)",
            },
        },
        "eligibility": {
            "passed": passed,
            "fail_reason": fail_reason,
            "checks": eligibility_checks,
        },
        "setup_detail": {
            "close": analysis.close,
            "ema20": analysis.ema20,
            "ema50": analysis.ema50,
            "rsi": analysis.rsi,
            "atr": analysis.atr,
            "macd_hist": analysis.macd_hist,
            "macd_hist_prev": analysis.macd_hist_prev,
            "bars_evaluated": analysis.bars_evaluated,
            "checks_passed": sum(1 for c in scored_checks if c.passed),
            "checks_total": len(scored_checks),
            "swing_score": swing_score,
            "base_score": base_score,
            "penalty_total": penalty_total,
            "quality_label": quality_label,
            "scored_side": scored_side,
            "rule_breakdown": rule_breakdown,
            "penalties": penalties,
            "notes": tier_reason,
        },
        "swing_checks": checks,
    }


def compute_swing_score(analysis: SwingAnalysis, df: pd.DataFrame | None = None) -> float:
    """Re-export for tests and callers."""
    from quant_hub.strategies.swing.scoring import compute_swing_score as _compute

    return _compute(analysis, df)
