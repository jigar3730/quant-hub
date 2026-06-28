import pandas as pd

from quant_hub.indicators import bollinger_width, find_swing_lows, is_rising, sma


def score_bollinger_compression(df: pd.DataFrame) -> float:
    close = df["Close"]
    width = bollinger_width(close, 20).dropna()
    if len(width) < 120:
        return 0.0
    history = width.tail(120)
    today = float(history.iloc[-1])
    pct_rank = float((history < today).mean())

    if pct_rank >= 0.5:
        return 0.0
    return 15.0 * (0.5 - pct_rank) / 0.5


def score_pattern_quality(df: pd.DataFrame) -> float:
    score = 0.0
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    price = float(close.iloc[-1])

    high_52w = float(high.tail(252).max())
    if high_52w > 0 and price >= high_52w * 0.90:
        score += 1.0

    recent = df.tail(20)
    band_low = float(recent["Low"].min())
    band_high = float(recent["High"].max())
    if band_low > 0 and (band_high - band_low) / band_low <= 0.15:
        score += 1.0

    swings = find_swing_lows(low.tail(60), order=2)
    if len(swings) >= 2 and swings[-1][1] > swings[-2][1]:
        score += 1.0

    sma10 = sma(close, 10)
    sma20 = sma(close, 20)
    if (
        float(sma10.iloc[-1]) > float(sma20.iloc[-1])
        and is_rising(sma10.dropna(), 5)
        and is_rising(sma20.dropna(), 5)
    ):
        score += 1.0

    if high_52w > 0:
        min_recent = float(close.tail(20).min())
        if min_recent >= high_52w * 0.88:
            score += 1.0

    return score
