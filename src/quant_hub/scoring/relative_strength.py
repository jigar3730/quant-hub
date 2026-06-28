import pandas as pd

from quant_hub.indicators import return_over_days


def _rs_ratio(stock_close: pd.Series, bench_close: pd.Series, days: int) -> float | None:
    stock_ret = return_over_days(stock_close, days)
    bench_ret = return_over_days(bench_close, days)
    if stock_ret is None or bench_ret is None or bench_ret == 0:
        return None
    return stock_ret / bench_ret


def compute_rs_market_ratio(stock_df: pd.DataFrame, spy_df: pd.DataFrame) -> float | None:
    stock_close = stock_df["Close"]
    spy_close = spy_df["Close"]
    r63 = _rs_ratio(stock_close, spy_close, 63)
    r126 = _rs_ratio(stock_close, spy_close, 126)
    if r63 is None and r126 is None:
        return None
    if r63 is None:
        return r126
    if r126 is None:
        return r63
    return (r63 + r126) / 2


def compute_rs_sector_ratio(
    stock_df: pd.DataFrame,
    sector_df: pd.DataFrame,
) -> float | None:
    stock_close = stock_df["Close"]
    sector_close = sector_df["Close"]
    r63 = _rs_ratio(stock_close, sector_close, 63)
    r126 = _rs_ratio(stock_close, sector_close, 126)
    if r63 is None and r126 is None:
        return None
    if r63 is None:
        return r126
    if r126 is None:
        return r63
    return (r63 + r126) / 2


def score_rs_market(ratios: pd.Series) -> pd.Series:
    """Percentile rank across universe, scaled to 0-20."""
    pct = ratios.rank(pct=True, na_option="keep")
    return (pct * 20).fillna(0)


def score_rs_sector(ratios: pd.Series, sector_etfs: pd.Series) -> pd.Series:
    """Percentile rank within each sector ETF group, scaled to 0-15."""
    scores = pd.Series(0.0, index=ratios.index)
    for etf in sector_etfs.dropna().unique():
        mask = sector_etfs == etf
        group = ratios[mask]
        if len(group) < 2:
            scores.loc[mask] = 0.0
            continue
        pct = group.rank(pct=True, na_option="keep")
        scores.loc[mask] = (pct * 15).fillna(0)
    return scores
