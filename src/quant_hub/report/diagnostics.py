import pandas as pd

from quant_hub.indicators import (
    bollinger_width,
    find_swing_lows,
    is_rising,
    sma,
)
from quant_hub.scoring.relative_strength import _rs_ratio
from quant_hub.scoring.volume import compute_accumulation_ratio


def rs_market_detail(stock_df: pd.DataFrame, spy_df: pd.DataFrame, score: float) -> dict:
    stock_close = stock_df["Close"]
    spy_close = spy_df["Close"]
    r63 = _rs_ratio(stock_close, spy_close, 63)
    r126 = _rs_ratio(stock_close, spy_close, 126)
    avg = None
    if r63 is not None and r126 is not None:
        avg = (r63 + r126) / 2
    elif r63 is not None:
        avg = r63
    elif r126 is not None:
        avg = r126

    if avg is None:
        meaning = "Insufficient data to compute relative strength vs SPY"
    elif avg > 1.2:
        meaning = "Strong outperformance vs SPY over 3-6 months"
    elif avg > 1.0:
        meaning = "Outperforming SPY over 3-6 months"
    elif avg > 0.8:
        meaning = "Roughly matching SPY"
    else:
        meaning = "Underperforming SPY over 3-6 months"

    return {
        "score": score,
        "max": 20,
        "raw": {
            "ratio_63d": round(r63, 3) if r63 else None,
            "ratio_126d": round(r126, 3) if r126 else None,
            "avg_ratio": round(avg, 3) if avg else None,
        },
        "meaning": meaning,
    }


def rs_sector_detail(
    stock_df: pd.DataFrame,
    sector_df: pd.DataFrame | None,
    sector_etf: str | None,
    score: float,
) -> dict:
    if sector_df is None or sector_df.empty:
        return {
            "score": score,
            "max": 15,
            "raw": {"sector_etf": sector_etf, "avg_ratio": None},
            "meaning": "No sector ETF data available",
        }

    stock_close = stock_df["Close"]
    sector_close = sector_df["Close"]
    r63 = _rs_ratio(stock_close, sector_close, 63)
    r126 = _rs_ratio(stock_close, sector_close, 126)
    avg = None
    if r63 is not None and r126 is not None:
        avg = (r63 + r126) / 2
    elif r63 is not None:
        avg = r63
    elif r126 is not None:
        avg = r126

    if avg is None:
        meaning = f"Insufficient data vs sector ETF {sector_etf}"
    elif avg > 1.2:
        meaning = f"Leading {sector_etf} sector peers"
    elif avg > 1.0:
        meaning = f"Outperforming {sector_etf} sector"
    else:
        meaning = f"Lagging {sector_etf} sector"

    return {
        "score": score,
        "max": 15,
        "raw": {
            "sector_etf": sector_etf,
            "ratio_63d": round(r63, 3) if r63 else None,
            "ratio_126d": round(r126, 3) if r126 else None,
            "avg_ratio": round(avg, 3) if avg else None,
        },
        "meaning": meaning,
    }


def accumulation_detail(df: pd.DataFrame, score: float) -> dict:
    ratio = compute_accumulation_ratio(df)
    if ratio is None:
        meaning = "Insufficient volume data"
    elif ratio > 1.5:
        meaning = "Heavy volume on up days vs down days (accumulation)"
    elif ratio > 1.0:
        meaning = "Moderate buying pressure on up days"
    else:
        meaning = "More volume on down days than up days (distribution)"

    return {
        "score": score,
        "max": 12,
        "raw": {"up_down_volume_ratio": round(ratio, 3) if ratio else None},
        "meaning": meaning,
    }


def relative_volume_detail(df: pd.DataFrame, score: float) -> dict:
    recent = df.tail(21)
    if len(recent) < 21:
        return {"score": score, "max": 8, "raw": {}, "meaning": "Insufficient data"}

    avg20 = float(recent["Volume"].iloc[:-1].mean())
    rel_1d = float(recent["Volume"].iloc[-1] / avg20) if avg20 else 0
    rel_3d = float(recent["Volume"].iloc[-3:].mean() / avg20) if avg20 else 0
    rel_vol = max(rel_1d, rel_3d)

    if rel_vol >= 2.0:
        meaning = "Strong volume surge (2x+ average)"
    elif rel_vol >= 1.5:
        meaning = "Elevated volume (1.5-2x average)"
    elif rel_vol >= 1.2:
        meaning = "Slightly above-average volume"
    else:
        meaning = "Normal volume, no short-term demand spike"

    return {
        "score": score,
        "max": 8,
        "raw": {
            "rel_volume_1d": round(rel_1d, 2),
            "rel_volume_3d": round(rel_3d, 2),
            "rel_volume_used": round(rel_vol, 2),
        },
        "meaning": meaning,
    }


def compression_detail(df: pd.DataFrame, score: float) -> dict:
    close = df["Close"]
    width = bollinger_width(close, 20).dropna()
    if len(width) < 120:
        return {"score": score, "max": 15, "raw": {}, "meaning": "Insufficient data"}

    history = width.tail(120)
    today = float(history.iloc[-1])
    pct_rank = float((history < today).mean())

    if pct_rank < 0.2:
        meaning = "Tight volatility squeeze; coiling for potential breakout"
    elif pct_rank < 0.5:
        meaning = "Moderate compression; some tightening"
    else:
        meaning = "Wide Bollinger bands; not compressed"

    return {
        "score": round(score, 2),
        "max": 15,
        "raw": {
            "bb_width": round(today, 4),
            "bb_width_percentile": round(pct_rank, 3),
        },
        "meaning": meaning,
    }


def pattern_detail(df: pd.DataFrame, score: float) -> dict:
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    price = float(close.iloc[-1])
    high_52w = float(high.tail(252).max())

    recent = df.tail(20)
    band_low = float(recent["Low"].min())
    band_high = float(recent["High"].max())
    swings = find_swing_lows(low.tail(60), order=2)
    sma10 = sma(close, 10)
    sma20 = sma(close, 20)

    checks = {
        "near_52w_high": high_52w > 0 and price >= high_52w * 0.90,
        "tight_20d_range": band_low > 0 and (band_high - band_low) / band_low <= 0.15,
        "higher_low": len(swings) >= 2 and swings[-1][1] > swings[-2][1],
        "rising_short_mas": (
            float(sma10.iloc[-1]) > float(sma20.iloc[-1])
            and is_rising(sma10.dropna(), 5)
            and is_rising(sma20.dropna(), 5)
        ),
        "no_sharp_pullback": high_52w > 0 and float(close.tail(20).min()) >= high_52w * 0.88,
    }

    passed = [k for k, v in checks.items() if v]
    return {
        "score": score,
        "max": 5,
        "raw": {"checks_passed": passed, "checks_total": 5, "checklist": checks},
        "meaning": f"{len(passed)}/5 pattern quality signals met",
    }


def resistance_detail(df: pd.DataFrame, score: float) -> dict:
    price = float(df["Close"].iloc[-1])
    high_50 = float(df["High"].tail(50).max())
    high_65 = float(df["High"].tail(65).max())
    resistance = max(high_50, high_65)
    distance_pct = (resistance - price) / resistance if resistance else None

    if distance_pct is not None and distance_pct <= 0.03:
        meaning = "Within 3% of resistance; breakout imminent"
    elif distance_pct is not None and distance_pct <= 0.08:
        meaning = "Approaching resistance (3-8% away)"
    else:
        meaning = "Far from near-term resistance"

    return {
        "score": score,
        "max": 5,
        "raw": {
            "resistance_level": round(resistance, 2),
            "distance_pct": round(distance_pct * 100, 2) if distance_pct else None,
        },
        "meaning": meaning,
    }


def revenue_detail(growth: float | None, score: float, *, status: str = "OK", source: str = "") -> dict:
    status_labels = {
        "OK": "",
        "MISSING": "Revenue growth data unavailable",
        "NOT_APPLICABLE": "Revenue growth not applicable for this issuer",
        "CAPPED": "Revenue growth capped at display limit (hypergrowth)",
        "NEGATIVE": None,
    }
    if status == "NEGATIVE" and growth is not None:
        meaning = f"Negative revenue growth ({growth * 100:.1f}% YoY)"
    elif status != "OK" and status != "NEGATIVE":
        meaning = status_labels.get(status, "Revenue growth data unavailable")
    elif growth is None:
        meaning = "Revenue growth data unavailable"
    elif growth >= 0.25:
        meaning = f"Strong revenue growth ({growth * 100:.1f}% YoY)"
    elif growth >= 0.05:
        meaning = f"Moderate revenue growth ({growth * 100:.1f}% YoY)"
    else:
        meaning = f"Weak or negative revenue growth ({growth * 100:.1f}% YoY)"

    if source:
        meaning = f"{meaning} [{source}]"

    return {
        "score": score,
        "max": 15,
        "status": status,
        "raw": {
            "revenue_yoy_pct": round(growth * 100, 2) if growth is not None else None,
            "source": source or None,
        },
        "meaning": meaning,
    }


def eps_detail(
    combined: float | None,
    score: float,
    *,
    status: str = "OK",
    source: str = "",
    eps_yoy: float | None = None,
    eps_cagr_3y: float | None = None,
) -> dict:
    if status == "NEGATIVE" and combined is not None:
        meaning = f"Negative EPS growth ({combined * 100:.1f}% blended)"
    elif status == "MISSING":
        meaning = "EPS growth data unavailable"
    elif status == "NOT_APPLICABLE":
        meaning = "EPS growth not applicable (e.g. negative earnings history)"
    elif status == "CAPPED":
        meaning = f"Strong EPS growth ({combined * 100:.1f}% blended, capped for scoring)"
    elif combined is None:
        meaning = "EPS growth data unavailable"
    elif combined >= 0.30:
        meaning = f"Strong EPS growth ({combined * 100:.1f}% blended)"
    elif combined >= 0.0:
        meaning = f"Moderate EPS growth ({combined * 100:.1f}% blended)"
    else:
        meaning = f"Negative EPS growth ({combined * 100:.1f}% blended)"

    if source:
        meaning = f"{meaning} [{source}]"

    return {
        "score": score,
        "max": 15,
        "status": status,
        "raw": {
            "eps_combined_pct": round(combined * 100, 2) if combined is not None else None,
            "eps_yoy_pct": round(eps_yoy * 100, 2) if eps_yoy is not None else None,
            "eps_cagr_3y_pct": round(eps_cagr_3y * 100, 2) if eps_cagr_3y is not None else None,
            "source": source or None,
        },
        "meaning": meaning,
    }


def fundamentals_detail_from_map(fund: dict, scores: dict | None = None) -> dict:
    """Build revenue/eps detail blocks from fundamentals snapshot + optional score row."""
    from quant_hub.scoring.fundamentals import score_eps, score_revenue

    rev_scored = score_revenue(
        fund.get("revenue_yoy"),
        status=fund.get("revenue_yoy_status", "MISSING"),
    )
    eps_scored = score_eps(
        fund.get("eps_combined"),
        status=fund.get("eps_combined_status", "MISSING"),
    )
    rev_score = float(scores.get("revenue_score", rev_scored.score)) if scores else rev_scored.score
    eps_score = float(scores.get("eps_score", eps_scored.score)) if scores else eps_scored.score
    return {
        "revenue": revenue_detail(
            fund.get("revenue_yoy"),
            rev_score,
            status=fund.get("revenue_yoy_status", rev_scored.status),
            source=fund.get("revenue_yoy_source", ""),
        ),
        "eps": eps_detail(
            fund.get("eps_combined"),
            eps_score,
            status=fund.get("eps_combined_status", eps_scored.status),
            source=fund.get("eps_source", ""),
            eps_yoy=fund.get("eps_yoy"),
            eps_cagr_3y=fund.get("eps_cagr_3y"),
        ),
    }


def score_components_detail(
    *,
    stock_df: pd.DataFrame,
    spy_df: pd.DataFrame,
    sector_df: pd.DataFrame | None,
    sector_etf: str | None,
    fund: dict,
    scores: dict,
) -> dict:
    return {
        "rs_market": rs_market_detail(stock_df, spy_df, scores["rs_market_score"]),
        "rs_sector": rs_sector_detail(stock_df, sector_df, sector_etf, scores["rs_sector_score"]),
        "accumulation": accumulation_detail(stock_df, scores["accumulation_score"]),
        "relative_volume": relative_volume_detail(stock_df, scores["relative_volume_score"]),
        "compression": compression_detail(stock_df, scores["compression_score"]),
        "pattern": pattern_detail(stock_df, scores["pattern_score"]),
        "resistance": resistance_detail(stock_df, scores["resistance_score"]),
        "revenue": revenue_detail(
            fund.get("revenue_yoy"),
            scores["revenue_score"],
            status=fund.get("revenue_yoy_status", "OK"),
            source=fund.get("revenue_yoy_source", ""),
        ),
        "eps": eps_detail(
            fund.get("eps_combined"),
            scores["eps_score"],
            status=fund.get("eps_combined_status", "OK"),
            source=fund.get("eps_source", ""),
            eps_yoy=fund.get("eps_yoy"),
            eps_cagr_3y=fund.get("eps_cagr_3y"),
        ),
    }
