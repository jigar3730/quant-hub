import pandas as pd


def score_resistance(df: pd.DataFrame) -> float:
    price = float(df["Close"].iloc[-1])
    high_50 = float(df["High"].tail(50).max())
    high_65 = float(df["High"].tail(65).max())
    resistance = max(high_50, high_65)
    if resistance == 0:
        return 0.0

    distance_pct = (resistance - price) / resistance
    if distance_pct <= 0.03:
        return 5.0
    if distance_pct <= 0.08:
        return 3.0
    return 0.0
