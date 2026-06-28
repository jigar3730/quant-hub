import pandas as pd


def compute_accumulation_ratio(df: pd.DataFrame, window: int = 20) -> float | None:
    recent = df.tail(window).copy()
    if len(recent) < window:
        return None
    prev_close = recent["Close"].shift(1)
    up = recent[recent["Close"] > prev_close]["Volume"].sum()
    down = recent[recent["Close"] < prev_close]["Volume"].sum()
    if down == 0:
        return None
    return float(up / down)


def score_accumulation(ratios: pd.Series) -> pd.Series:
    pct = ratios.rank(pct=True, na_option="keep")
    return (pct * 12).fillna(0)


def score_relative_volume(df: pd.DataFrame) -> float:
    recent = df.tail(21)
    if len(recent) < 21:
        return 0.0
    avg20 = float(recent["Volume"].iloc[:-1].mean())
    if avg20 == 0:
        return 0.0
    rel_1d = float(recent["Volume"].iloc[-1] / avg20)
    rel_3d = float(recent["Volume"].iloc[-3:].mean() / avg20)
    rel_vol = max(rel_1d, rel_3d)

    if rel_vol >= 2.0:
        return 8.0
    if rel_vol >= 1.5:
        return 5.0
    if rel_vol >= 1.2:
        return 3.0
    return 0.0
