from dataclasses import dataclass

import pandas as pd

from quant_hub.indicators import distance_from_high_pct, return_over_days, sma


@dataclass(frozen=True)
class MarketRegime:
    label: str
    multiplier: float


def compute_market_regime(spy_df: pd.DataFrame) -> MarketRegime:
    """Classify SPY market regime and return score multiplier."""
    detail = regime_detail(spy_df)
    return MarketRegime(detail["label"], detail["multiplier"])


def regime_detail(spy_df: pd.DataFrame) -> dict:
    """Return regime classification with SPY indicator values."""
    close = spy_df["Close"]
    price = float(close.iloc[-1])
    sma50 = float(sma(close, 50).iloc[-1])
    sma200 = float(sma(close, 200).iloc[-1])
    ret_63 = return_over_days(close, 63) or 0.0

    high_52w = float(spy_df["High"].tail(252).max())
    dist_from_high = distance_from_high_pct(price, high_52w) or 0.0

    strong = price > sma50 and sma50 > sma200 and ret_63 > 0
    weak = price < sma200 or dist_from_high > 0.10

    if strong:
        label, multiplier = "strong", 1.0
        meaning = "SPY in uptrend; full score weight applied"
    elif weak:
        label, multiplier = "weak", 0.6
        meaning = "SPY below 200-day MA or >10% off highs; scores discounted 40%"
    else:
        label, multiplier = "neutral", 0.85
        meaning = "Mixed market conditions; scores discounted 15%"

    return {
        "label": label,
        "multiplier": multiplier,
        "meaning": meaning,
        "spy_price": round(price, 2),
        "sma50": round(sma50, 2),
        "sma200": round(sma200, 2),
        "return_63d_pct": round(ret_63 * 100, 2),
        "pct_below_52w_high": round(dist_from_high * 100, 2),
        "high_52w": round(high_52w, 2),
    }
