"""Shared quarterly fundamental series helpers."""

from __future__ import annotations

import pandas as pd


def quarterly_series(statement: pd.DataFrame, field: str) -> pd.Series:
    if statement is None or statement.empty or field not in statement.index:
        return pd.Series(dtype=float)
    series = statement.loc[field].dropna()
    series.index = pd.to_datetime(series.index)
    return series.sort_index()


def cagr(series: pd.Series, years: float = 3.0) -> float | None:
    quarters = int(years * 4)
    if len(series) <= quarters:
        return None
    recent = series.iloc[-1]
    prior = series.iloc[-1 - quarters]
    if prior <= 0 or recent <= 0 or pd.isna(prior) or pd.isna(recent):
        return None
    return (recent / prior) ** (1 / years) - 1
