"""Fine-grained swing setup quality scoring — partial credit + penalties."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

SWING_RULE_POINTS = 20
SWING_RULE_COUNT = 5
SWING_MAX_PENALTY = 25.0

SWING_SCORE_RUBRIC: tuple[tuple[str, str], ...] = (
    ("Trend alignment", "EMA20 vs EMA50 — full credit when spread is clear on the setup side."),
    ("EMA50 slope", "50-week EMA rising (long) or falling (short) — partial if flat."),
    ("Pullback zone", "Close near 20 EMA — partial credit by ATR distance from band."),
    ("RSI band", "RSI in setup range — partial when slightly outside band."),
    ("MACD momentum", "Two-week histogram trend + not overextended — scored in sub-parts."),
)

SWING_PENALTY_RUBRIC: tuple[tuple[str, str], ...] = (
    ("Chase / extended", "Long: close well above EMA20 band. Short: well below band."),
    ("RSI extreme", "Overbought on long or oversold on short entry."),
    ("MACD overextension", "Histogram stretched vs 20-week std — late entry risk."),
    ("Structure break", "Long below EMA50 or short above EMA50."),
    ("Wrong-side dominance", "Opposite side rules pass more than scored side."),
    ("Weak weekly close", "Long: close in bottom 25% of week range (weak acceptance)."),
)

QUALITY_LABELS = (
    (85.0, "A — High quality"),
    (70.0, "B — Valid setup"),
    (55.0, "C — Near-miss / soft"),
    (0.0, "D — Avoid"),
)


@dataclass(frozen=True)
class SwingScoreResult:
    base_score: float
    penalty_total: float
    swing_score: float
    quality_label: str
    rule_breakdown: list[dict]
    penalties: list[dict]
    scored_side: str


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def quality_label(score: float) -> str:
    for threshold, label in QUALITY_LABELS:
        if score >= threshold:
            return label
    return QUALITY_LABELS[-1][1]


def _scored_side(analysis: Any) -> str:
    if analysis.setup:
        return "long" if analysis.setup.setup_type == "SETUP_LONG" else "short"
    return analysis.candidate if analysis.candidate in ("long", "short") else "long"


def _trend_points(side: str, ema20: float, ema50: float) -> tuple[float, bool]:
    if ema50 <= 0:
        return 0.0, False
    spread_pct = (ema20 - ema50) / ema50 * 100.0
    if side == "long":
        if ema20 <= ema50:
            return 0.0, False
        if spread_pct >= 2.0:
            return float(SWING_RULE_POINTS), True
        if spread_pct >= 1.0:
            return 16.0, True
        if spread_pct >= 0.3:
            return 12.0, True
        return 8.0, True
    if ema20 >= ema50:
        return 0.0, False
    spread_pct = abs(spread_pct)
    if spread_pct >= 2.0:
        return float(SWING_RULE_POINTS), True
    if spread_pct >= 1.0:
        return 16.0, True
    if spread_pct >= 0.3:
        return 12.0, True
    return 8.0, True


def _ema50_slope_points(side: str, ema50: float, ema50_prev: float) -> tuple[float, bool]:
    if ema50_prev <= 0:
        return 0.0, False
    delta_pct = (ema50 - ema50_prev) / ema50_prev * 100.0
    if side == "long":
        if delta_pct >= 0.2:
            return float(SWING_RULE_POINTS), True
        if delta_pct >= 0.05:
            return 14.0, True
        if delta_pct >= 0:
            return 8.0, False
        return 0.0, False
    if delta_pct <= -0.2:
        return float(SWING_RULE_POINTS), True
    if delta_pct <= -0.05:
        return 14.0, True
    if delta_pct <= 0:
        return 8.0, False
    return 0.0, False


def _pullback_points(
    side: str,
    close: float,
    ema20: float,
    atr: float,
) -> tuple[float, bool]:
    if ema20 <= 0:
        return 0.0, False
    atr = max(atr, ema20 * 0.005)
    if side == "long":
        lo, hi = ema20, ema20 * 1.02
        if lo <= close <= hi:
            return float(SWING_RULE_POINTS), True
        if close > hi:
            dist = (close - hi) / atr
            return _clamp(20.0 - dist * 7.0, 0.0, 18.0), False
        dist = (lo - close) / atr
        return _clamp(16.0 - dist * 6.0, 0.0, 16.0), False
    lo, hi = ema20 * 0.98, ema20
    if lo <= close <= hi:
        return float(SWING_RULE_POINTS), True
    if close < lo:
        dist = (lo - close) / atr
        return _clamp(20.0 - dist * 7.0, 0.0, 18.0), False
    dist = (close - hi) / atr
    return _clamp(16.0 - dist * 6.0, 0.0, 16.0), False


def _rsi_points(side: str, rsi: float, *, rsi_min_long: float = 45.0) -> tuple[float, bool]:
    if side == "long":
        lo, hi = rsi_min_long, 60.0
        if lo <= rsi <= hi:
            return float(SWING_RULE_POINTS), True
        if hi < rsi <= hi + 8:
            return _clamp(20.0 - (rsi - hi) * 1.5, 6.0, 16.0), False
        if lo - 6 <= rsi < lo:
            return _clamp(12.0 - (lo - rsi) * 0.8, 4.0, 12.0), False
        if rsi > 70:
            return 0.0, False
        return 4.0, False
    lo, hi = 50.0, 65.0
    if lo <= rsi <= hi:
        return float(SWING_RULE_POINTS), True
    if lo - 8 <= rsi < lo:
        return _clamp(20.0 - (lo - rsi) * 1.5, 6.0, 16.0), False
    if hi < rsi <= hi + 6:
        return _clamp(12.0 - (rsi - hi) * 0.8, 4.0, 12.0), False
    if rsi < 35:
        return 0.0, False
    return 4.0, False


def _macd_points(side: str, df: pd.DataFrame) -> tuple[float, bool]:
    h = df["MACD_Hist"].tail(3)
    if len(h) < 3:
        return 0.0, False
    hist_std = float(df["MACD_Hist"].rolling(20).std().iloc[-1] or 0.0)
    latest = float(h.iloc[-1])
    prev = float(h.iloc[-2])
    prior = float(h.iloc[-3])
    points = 0.0
    if side == "long":
        if latest > prev:
            points += 10.0
        if prev > prior:
            points += 10.0
        passed = points >= 20.0 and (hist_std <= 0 or latest < hist_std * 2)
        if hist_std > 0 and latest >= hist_std * 2:
            points = max(0.0, points - 8.0)
        return min(points, float(SWING_RULE_POINTS)), passed
    if latest < prev:
        points += 10.0
    if prev < prior:
        points += 10.0
    passed = points >= 20.0 and (hist_std <= 0 or latest > -hist_std * 2)
    if hist_std > 0 and latest <= -hist_std * 2:
        points = max(0.0, points - 8.0)
    return min(points, float(SWING_RULE_POINTS)), passed


def _rule_row(
    rule: str,
    label: str,
    points: float,
    *,
    passed: bool,
    threshold: str,
    detail: str = "",
) -> dict:
    return {
        "rule": rule,
        "label": label,
        "passed": passed,
        "score": round(points, 1),
        "max": float(SWING_RULE_POINTS),
        "threshold": threshold,
        "detail": detail,
    }


def _build_rule_breakdown(
    analysis: Any,
    side: str,
    df: pd.DataFrame,
    *,
    rsi_min_long: float,
) -> list[dict]:
    checks = analysis.setup_checks()
    check_by_rule = {c.rule: c for c in checks}
    close = float(analysis.close or 0)
    ema20 = float(analysis.ema20 or 0)
    ema50 = float(analysis.ema50 or 0)
    atr = float(analysis.atr or 0)
    rsi = float(analysis.rsi or 0)

    prev_ema50 = ema50
    if side == "long" and analysis.long_checks:
        val = analysis.long_checks[1].value
        if isinstance(val, dict):
            prev_ema50 = float(val.get("ema50_prev", ema50))
    elif side == "short" and analysis.short_checks:
        val = analysis.short_checks[1].value
        if isinstance(val, dict):
            prev_ema50 = float(val.get("ema50_prev", ema50))

    trend_pts, trend_pass = _trend_points(side, ema20, ema50)
    slope_pts, slope_pass = _ema50_slope_points(side, ema50, prev_ema50)
    pull_pts, pull_pass = _pullback_points(side, close, ema20, atr)
    rsi_pts, rsi_pass = _rsi_points(side, rsi, rsi_min_long=rsi_min_long)
    macd_pts, macd_pass = _macd_points(side, df)

    prefix = f"{side}_"
    labels = {
        f"{prefix}trend": "Uptrend (EMA20 > EMA50)" if side == "long" else "Downtrend (EMA20 < EMA50)",
        f"{prefix}ema50_rising": "EMA50 rising" if side == "long" else "EMA50 falling",
        f"{prefix}pullback_zone": "Pullback into 20 EMA",
        f"{prefix}rsi_band": "RSI in long band" if side == "long" else "RSI in short band",
        f"{prefix}macd_momentum": "MACD histogram momentum",
    }
    thresholds = {c.rule: c.threshold for c in checks}
    passes = {
        f"{prefix}trend": trend_pass,
        f"{prefix}ema50_rising": slope_pass,
        f"{prefix}pullback_zone": pull_pass,
        f"{prefix}rsi_band": rsi_pass,
        f"{prefix}macd_momentum": macd_pass,
    }
    points_map = {
        f"{prefix}trend": trend_pts,
        f"{prefix}ema50_rising": slope_pts,
        f"{prefix}pullback_zone": pull_pts,
        f"{prefix}rsi_band": rsi_pts,
        f"{prefix}macd_momentum": macd_pts,
    }

    rows: list[dict] = []
    for key in (
        f"{prefix}trend",
        f"{prefix}ema50_rising",
        f"{prefix}pullback_zone",
        f"{prefix}rsi_band",
        f"{prefix}macd_momentum",
    ):
        chk = check_by_rule.get(key)
        rows.append(
            _rule_row(
                key,
                labels[key],
                points_map[key],
                passed=passes[key],
                threshold=thresholds.get(key, chk.threshold if chk else ""),
                detail=chk.detail if chk else "",
            )
        )
    return rows


def _penalty(
    code: str,
    label: str,
    amount: float,
    *,
    reason: str,
) -> dict:
    return {
        "code": code,
        "label": label,
        "amount": round(-abs(amount), 1),
        "reason": reason,
    }


def _compute_penalties(
    analysis: Any,
    side: str,
    df: pd.DataFrame,
    *,
    rsi_min_long: float,
) -> list[dict]:
    penalties: list[dict] = []
    close = float(analysis.close or 0)
    ema20 = float(analysis.ema20 or 0)
    ema50 = float(analysis.ema50 or 0)
    rsi = float(analysis.rsi or 0)
    atr = max(float(analysis.atr or 0), ema20 * 0.005)

    long_pass = sum(1 for c in analysis.long_checks if c.passed)
    short_pass = sum(1 for c in analysis.short_checks if c.passed)

    if side == "long":
        if close > ema20 * 1.05:
            penalties.append(
                _penalty(
                    "chase",
                    "Chase / extended",
                    10.0,
                    reason=f"Close ${close:.2f} > 5% above EMA20 (${ema20:.2f})",
                )
            )
        elif close > ema20 * 1.02 and not any(p["code"] == "chase" for p in penalties):
            excess = (close - ema20 * 1.02) / atr
            if excess > 0.5:
                penalties.append(
                    _penalty(
                        "extended",
                        "Chase / extended",
                        min(8.0, 4.0 + excess * 2),
                        reason="Above pullback band — entry extended",
                    )
                )
        if rsi > 72:
            penalties.append(
                _penalty("rsi_extreme", "RSI extreme", 12.0, reason=f"RSI {rsi:.1f} — overbought for long")
            )
        elif rsi > 68:
            penalties.append(
                _penalty("rsi_extreme", "RSI extreme", 8.0, reason=f"RSI {rsi:.1f} — stretched for long")
            )
        if close < ema50:
            penalties.append(
                _penalty(
                    "structure_break",
                    "Structure break",
                    10.0,
                    reason=f"Close below EMA50 (${ema50:.2f})",
                )
            )
        if short_pass > long_pass + 1:
            penalties.append(
                _penalty(
                    "wrong_side",
                    "Wrong-side dominance",
                    8.0,
                    reason=f"Short rules {short_pass}/5 vs long {long_pass}/5",
                )
            )
    else:
        if close < ema20 * 0.95:
            penalties.append(
                _penalty(
                    "chase",
                    "Chase / extended",
                    10.0,
                    reason=f"Close ${close:.2f} > 5% below EMA20 (${ema20:.2f})",
                )
            )
        if rsi < 32:
            penalties.append(
                _penalty("rsi_extreme", "RSI extreme", 12.0, reason=f"RSI {rsi:.1f} — oversold for short")
            )
        elif rsi < 38:
            penalties.append(
                _penalty("rsi_extreme", "RSI extreme", 8.0, reason=f"RSI {rsi:.1f} — stretched for short")
            )
        if close > ema50:
            penalties.append(
                _penalty(
                    "structure_break",
                    "Structure break",
                    10.0,
                    reason=f"Close above EMA50 (${ema50:.2f})",
                )
            )
        if long_pass > short_pass + 1:
            penalties.append(
                _penalty(
                    "wrong_side",
                    "Wrong-side dominance",
                    8.0,
                    reason=f"Long rules {long_pass}/5 vs short {short_pass}/5",
                )
            )

    hist_std = float(df["MACD_Hist"].rolling(20).std().iloc[-1] or 0.0)
    macd = float(analysis.macd_hist or 0)
    if hist_std > 0:
        if side == "long" and macd >= hist_std * 2:
            penalties.append(
                _penalty(
                    "macd_overext",
                    "MACD overextension",
                    8.0,
                    reason="Histogram > 2× 20-week std — late momentum",
                )
            )
        elif side == "short" and macd <= -hist_std * 2:
            penalties.append(
                _penalty(
                    "macd_overext",
                    "MACD overextension",
                    8.0,
                    reason="Histogram < −2× 20-week std — late momentum",
                )
            )

    latest = df.iloc[-1]
    high = float(latest.get("High", close))
    low = float(latest.get("Low", close))
    span = high - low
    if span > 0 and side == "long":
        position = (close - low) / span
        if position < 0.25:
            penalties.append(
                _penalty(
                    "weak_close",
                    "Weak weekly close",
                    5.0,
                    reason="Close in bottom 25% of weekly range",
                )
            )
    elif span > 0 and side == "short":
        position = (close - low) / span
        if position > 0.75:
            penalties.append(
                _penalty(
                    "weak_close",
                    "Weak weekly close",
                    5.0,
                    reason="Close in top 25% of weekly range (short)",
                )
            )

    total = sum(abs(p["amount"]) for p in penalties)
    if total > SWING_MAX_PENALTY:
        scale = SWING_MAX_PENALTY / total
        for p in penalties:
            p["amount"] = round(p["amount"] * scale, 1)
    return penalties


def score_swing_quality(
    analysis: Any,
    df: pd.DataFrame,
    *,
    rsi_min_long: float = 45.0,
) -> SwingScoreResult:
    """Partial credit base score minus capped penalties → 0–100 quality score."""
    side = _scored_side(analysis)
    rule_breakdown = _build_rule_breakdown(analysis, side, df, rsi_min_long=rsi_min_long)
    base_score = round(sum(item["score"] for item in rule_breakdown), 1)
    penalties = _compute_penalties(analysis, side, df, rsi_min_long=rsi_min_long)
    penalty_total = round(sum(p["amount"] for p in penalties), 1)
    swing_score = round(_clamp(base_score + penalty_total, 0.0, 100.0), 1)
    return SwingScoreResult(
        base_score=base_score,
        penalty_total=penalty_total,
        swing_score=swing_score,
        quality_label=quality_label(swing_score),
        rule_breakdown=rule_breakdown,
        penalties=penalties,
        scored_side=side,
    )


def compute_swing_score(analysis: Any, df: pd.DataFrame | None = None) -> float:
    """Return quality score; uses cached result when attached to analysis."""
    cached = getattr(analysis, "score_result", None)
    if cached is not None:
        return cached.swing_score
    if df is None:
        return 0.0
    return score_swing_quality(analysis, df).swing_score
