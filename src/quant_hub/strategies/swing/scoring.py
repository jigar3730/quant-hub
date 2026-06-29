"""Fine-grained swing setup quality scoring — partial credit + penalties."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from quant_hub.strategies.swing.constants import (
    CHASE_ATR_THRESHOLD,
    SWING_CORE_RULE_POINTS,
    SWING_MAX_BASE,
    SWING_RS_POINTS,
    SWING_RULE_COUNT,
    SWING_VOLUME_POINTS,
)
from quant_hub.strategies.swing.metrics import pullback_zone

SWING_RULE_POINTS = SWING_CORE_RULE_POINTS  # backward compat for dashboard guide
SWING_MAX_PENALTY = 25.0

SWING_SCORE_RUBRIC: tuple[tuple[str, str], ...] = (
    ("Trend alignment", "EMA20 vs EMA50 — full credit when spread is clear on the setup side."),
    ("EMA50 slope", "50-week EMA rising (long) or falling (short) — partial if flat."),
    (
        "Pullback zone",
        "Close within ATR band around 20 EMA — full credit in zone; partial by ATR distance.",
    ),
    ("RSI band", "RSI in setup range — partial when slightly outside band."),
    ("MACD momentum", "Two-week histogram trend + not overextended — scored in sub-parts."),
    ("RS vs SPY", "13w + 26w return ratio vs SPY — universe percentile when available."),
    ("Pullback volume", "Dry pullback week vs 10-week average — lower volume scores higher."),
)

SWING_PENALTY_RUBRIC: tuple[tuple[str, str], ...] = (
    ("Chase / extended", "Long: close beyond ATR pullback band. Short: mirror below band."),
    ("RSI extreme", "Overbought on long or oversold on short entry."),
    ("MACD overextension", "Histogram stretched vs 20-week std — late entry risk."),
    ("Structure break", "Long below EMA50 or short above EMA50."),
    ("Wrong-side dominance", "Opposite side rules pass more than scored side."),
    ("Weak weekly close", "Long: close in bottom 25% of week range (weak acceptance)."),
    ("RS laggard", "Long setup with RS ratio vs SPY below 0.90."),
    ("Heavy pullback volume", "Pullback week volume > 130% of 10-week average."),
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
    rs_ratio_score: float = 0.0
    volume_score: float = 0.0


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
    pts = float(SWING_CORE_RULE_POINTS)
    if ema50 <= 0:
        return 0.0, False
    spread_pct = (ema20 - ema50) / ema50 * 100.0
    if side == "long":
        if ema20 <= ema50:
            return 0.0, False
        if spread_pct >= 2.0:
            return pts, True
        if spread_pct >= 1.0:
            return pts * 0.8, True
        if spread_pct >= 0.3:
            return pts * 0.6, True
        return pts * 0.4, True
    if ema20 >= ema50:
        return 0.0, False
    spread_pct = abs(spread_pct)
    if spread_pct >= 2.0:
        return pts, True
    if spread_pct >= 1.0:
        return pts * 0.8, True
    if spread_pct >= 0.3:
        return pts * 0.6, True
    return pts * 0.4, True


def _ema50_slope_points(side: str, ema50: float, ema50_prev: float) -> tuple[float, bool]:
    pts = float(SWING_CORE_RULE_POINTS)
    if ema50_prev <= 0:
        return 0.0, False
    delta_pct = (ema50 - ema50_prev) / ema50_prev * 100.0
    if side == "long":
        if delta_pct >= 0.2:
            return pts, True
        if delta_pct >= 0.05:
            return pts * 0.7, True
        if delta_pct >= 0:
            return pts * 0.4, False
        return 0.0, False
    if delta_pct <= -0.2:
        return pts, True
    if delta_pct <= -0.05:
        return pts * 0.7, True
    if delta_pct <= 0:
        return pts * 0.4, False
    return 0.0, False


def _pullback_points(
    side: str,
    close: float,
    ema20: float,
    atr: float,
) -> tuple[float, bool]:
    if ema20 <= 0:
        return 0.0, False
    pts = float(SWING_CORE_RULE_POINTS)
    lo, hi, in_zone = pullback_zone(side, close, ema20, atr)
    atr = max(atr, ema20 * 0.005)
    if in_zone:
        return pts, True
    if side == "long":
        if close > hi:
            dist = (close - hi) / atr
            return _clamp(pts - dist * (pts * 0.35), 0.0, pts * 0.9), False
        dist = (lo - close) / atr
        return _clamp(pts * 0.8 - dist * (pts * 0.3), 0.0, pts * 0.8), False
    if close < lo:
        dist = (lo - close) / atr
        return _clamp(pts - dist * (pts * 0.35), 0.0, pts * 0.9), False
    dist = (close - hi) / atr
    return _clamp(pts * 0.8 - dist * (pts * 0.3), 0.0, pts * 0.8), False


def _rsi_points(side: str, rsi: float, *, rsi_min_long: float = 45.0) -> tuple[float, bool]:
    pts = float(SWING_CORE_RULE_POINTS)
    if side == "long":
        lo, hi = rsi_min_long, 60.0
        if lo <= rsi <= hi:
            return pts, True
        if hi < rsi <= hi + 8:
            return _clamp(pts - (rsi - hi) * (pts * 0.075), pts * 0.3, pts * 0.8), False
        if lo - 6 <= rsi < lo:
            return _clamp(pts * 0.6 - (lo - rsi) * (pts * 0.04), pts * 0.2, pts * 0.6), False
        if rsi > 70:
            return 0.0, False
        return pts * 0.2, False
    lo, hi = 50.0, 65.0
    if lo <= rsi <= hi:
        return pts, True
    if lo - 8 <= rsi < lo:
        return _clamp(pts - (lo - rsi) * (pts * 0.075), pts * 0.3, pts * 0.8), False
    if hi < rsi <= hi + 6:
        return _clamp(pts * 0.6 - (rsi - hi) * (pts * 0.04), pts * 0.2, pts * 0.6), False
    if rsi < 35:
        return 0.0, False
    return pts * 0.2, False


def _macd_points(side: str, df: pd.DataFrame) -> tuple[float, bool]:
    pts = float(SWING_CORE_RULE_POINTS)
    half = pts / 2
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
            points += half
        if prev > prior:
            points += half
        passed = points >= pts and (hist_std <= 0 or latest < hist_std * 2)
        if hist_std > 0 and latest >= hist_std * 2:
            points = max(0.0, points - pts * 0.4)
        return min(points, pts), passed
    if latest < prev:
        points += half
    if prev < prior:
        points += half
    passed = points >= pts and (hist_std <= 0 or latest > -hist_std * 2)
    if hist_std > 0 and latest <= -hist_std * 2:
        points = max(0.0, points - pts * 0.4)
    return min(points, pts), passed


def _rs_points(side: str, analysis: Any) -> tuple[float, bool]:
    pts = float(SWING_RS_POINTS)
    ratio = getattr(analysis, "rs_ratio", None)
    percentile = getattr(analysis, "rs_percentile", None)
    if percentile is not None:
        if side == "long":
            if percentile >= 0.85:
                return pts, True
            if percentile >= 0.65:
                return pts * 0.7, True
            if percentile >= 0.45:
                return pts * 0.4, False
            return pts * 0.15, False
        if percentile <= 0.15:
            return pts, True
        if percentile <= 0.35:
            return pts * 0.7, True
        if percentile <= 0.55:
            return pts * 0.4, False
        return pts * 0.15, False
    if ratio is None:
        return 0.0, False
    if side == "long":
        if ratio >= 1.15:
            return pts, True
        if ratio >= 1.0:
            return pts * 0.7, True
        if ratio >= 0.9:
            return pts * 0.4, False
        return 0.0, False
    if ratio <= 0.85:
        return pts, True
    if ratio <= 1.0:
        return pts * 0.7, True
    if ratio <= 1.1:
        return pts * 0.4, False
    return 0.0, False


def _volume_points(side: str, vol_ratio: float | None) -> tuple[float, bool]:
    pts = float(SWING_VOLUME_POINTS)
    if vol_ratio is None:
        return 0.0, False
    if vol_ratio < 0.75:
        return pts, True
    if vol_ratio < 0.85:
        return pts * 0.6, True
    if vol_ratio <= 1.1:
        return pts * 0.2, False
    if vol_ratio > 1.3:
        return 0.0, False
    return pts * 0.1, False


def _rule_row(
    rule: str,
    label: str,
    points: float,
    *,
    passed: bool,
    threshold: str,
    detail: str = "",
    max_points: float | None = None,
) -> dict:
    cap = max_points if max_points is not None else float(SWING_CORE_RULE_POINTS)
    return {
        "rule": rule,
        "label": label,
        "passed": passed,
        "score": round(points, 1),
        "max": cap,
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
    rs_pts, rs_pass = _rs_points(side, analysis)
    vol_pts, vol_pass = _volume_points(side, getattr(analysis, "vol_ratio", None))

    prefix = f"{side}_"
    labels = {
        f"{prefix}trend": "Uptrend (EMA20 > EMA50)" if side == "long" else "Downtrend (EMA20 < EMA50)",
        f"{prefix}ema50_rising": "EMA50 rising" if side == "long" else "EMA50 falling",
        f"{prefix}pullback_zone": "Pullback into 20 EMA (ATR band)",
        f"{prefix}rsi_band": "RSI in long band" if side == "long" else "RSI in short band",
        f"{prefix}macd_momentum": "MACD histogram momentum",
        "rs_market": "RS vs SPY (13w + 26w)",
        "volume_pullback": "Pullback volume vs 10-week avg",
    }
    thresholds = {c.rule: c.threshold for c in checks}
    passes = {
        f"{prefix}trend": trend_pass,
        f"{prefix}ema50_rising": slope_pass,
        f"{prefix}pullback_zone": pull_pass,
        f"{prefix}rsi_band": rsi_pass,
        f"{prefix}macd_momentum": macd_pass,
        "rs_market": rs_pass,
        "volume_pullback": vol_pass,
    }
    points_map = {
        f"{prefix}trend": trend_pts,
        f"{prefix}ema50_rising": slope_pts,
        f"{prefix}pullback_zone": pull_pts,
        f"{prefix}rsi_band": rsi_pts,
        f"{prefix}macd_momentum": macd_pts,
        "rs_market": rs_pts,
        "volume_pullback": vol_pts,
    }
    max_map = {
        "rs_market": float(SWING_RS_POINTS),
        "volume_pullback": float(SWING_VOLUME_POINTS),
    }

    core_keys = (
        f"{prefix}trend",
        f"{prefix}ema50_rising",
        f"{prefix}pullback_zone",
        f"{prefix}rsi_band",
        f"{prefix}macd_momentum",
    )
    rows: list[dict] = []
    for key in (*core_keys, "rs_market", "volume_pullback"):
        chk = check_by_rule.get(key)
        detail = ""
        if key == "rs_market":
            ratio = getattr(analysis, "rs_ratio", None)
            pct = getattr(analysis, "rs_percentile", None)
            if ratio is not None:
                detail = f"ratio={ratio:.2f}"
            if pct is not None:
                detail = f"{detail}, pct={pct:.0%}".strip(", ")
        elif key == "volume_pullback":
            vr = getattr(analysis, "vol_ratio", None)
            if vr is not None:
                detail = f"vol_ratio={vr:.2f}"
        rows.append(
            _rule_row(
                key,
                labels[key],
                points_map[key],
                passed=passes[key],
                threshold=thresholds.get(key, chk.threshold if chk else ""),
                detail=detail or (chk.detail if chk else ""),
                max_points=max_map.get(key),
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
    vol_ratio = getattr(analysis, "vol_ratio", None)
    rs_ratio = getattr(analysis, "rs_ratio", None)

    lo, hi, in_zone = pullback_zone(side, close, ema20, atr)

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
        elif not in_zone and close > hi:
            excess = (close - hi) / atr
            if excess > CHASE_ATR_THRESHOLD:
                penalties.append(
                    _penalty(
                        "extended",
                        "Chase / extended",
                        min(8.0, 4.0 + excess * 2),
                        reason="Above ATR pullback band — entry extended",
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
        if rs_ratio is not None and rs_ratio < 0.9:
            penalties.append(
                _penalty(
                    "rs_laggard",
                    "RS laggard",
                    8.0 if rs_ratio < 0.8 else 5.0,
                    reason=f"RS vs SPY {rs_ratio:.2f} — underperforming market",
                )
            )
        if vol_ratio is not None and vol_ratio > 1.3:
            penalties.append(
                _penalty(
                    "heavy_volume",
                    "Heavy pullback volume",
                    min(8.0, 4.0 + (vol_ratio - 1.3) * 5),
                    reason=f"Pullback volume {vol_ratio:.0%} of 10-week avg",
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
        elif not in_zone and close < lo:
            excess = (lo - close) / atr
            if excess > CHASE_ATR_THRESHOLD:
                penalties.append(
                    _penalty(
                        "extended",
                        "Chase / extended",
                        min(8.0, 4.0 + excess * 2),
                        reason="Below ATR pullback band — entry extended",
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
        if rs_ratio is not None and rs_ratio > 1.1:
            penalties.append(
                _penalty(
                    "rs_leader",
                    "RS laggard",
                    8.0 if rs_ratio > 1.25 else 5.0,
                    reason=f"RS vs SPY {rs_ratio:.2f} — outperforming (weak short context)",
                )
            )
        if vol_ratio is not None and vol_ratio > 1.3:
            penalties.append(
                _penalty(
                    "heavy_volume",
                    "Heavy pullback volume",
                    min(8.0, 4.0 + (vol_ratio - 1.3) * 5),
                    reason=f"Pullback volume {vol_ratio:.0%} of 10-week avg",
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
    """Partial credit base score (max 100) minus capped penalties → 0–100 quality score."""
    side = _scored_side(analysis)
    rule_breakdown = _build_rule_breakdown(analysis, side, df, rsi_min_long=rsi_min_long)
    rs_pts = next((r["score"] for r in rule_breakdown if r["rule"] == "rs_market"), 0.0)
    vol_pts = next((r["score"] for r in rule_breakdown if r["rule"] == "volume_pullback"), 0.0)
    base_score = round(min(sum(item["score"] for item in rule_breakdown), SWING_MAX_BASE), 1)
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
        rs_ratio_score=rs_pts,
        volume_score=vol_pts,
    )


def compute_swing_score(analysis: Any, df: pd.DataFrame | None = None) -> float:
    """Return quality score; uses cached result when attached to analysis."""
    cached = getattr(analysis, "score_result", None)
    if cached is not None:
        return cached.swing_score
    if df is None:
        return 0.0
    return score_swing_quality(analysis, df).swing_score
