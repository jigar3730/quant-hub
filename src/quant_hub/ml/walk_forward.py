"""Walk-forward date splits for ML training and evaluation (no random shuffle)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    split_date: date
    train_dates: tuple[date, ...]
    test_dates: tuple[date, ...]


def unique_sorted_dates(dates: list[date] | pd.Series) -> list[date]:
    series = dates if isinstance(dates, pd.Series) else pd.Series(dates)
    parsed = pd.to_datetime(series).dt.date.unique().tolist()
    return sorted(set(parsed))


def simple_holdout_split(
    scan_dates: list[date],
    *,
    split_date: date,
) -> tuple[list[date], list[date]]:
    """Train on weeks strictly before split_date; test on split_date and after."""
    train = [d for d in scan_dates if d < split_date]
    test = [d for d in scan_dates if d >= split_date]
    return train, test


def iter_walk_forward_folds(
    scan_dates: list[date],
    *,
    train_weeks: int = 52,
    test_weeks: int = 13,
    step_weeks: int | None = None,
) -> list[WalkForwardFold]:
    """
    Rolling walk-forward folds over sorted weekly scan dates.

    Each fold uses `train_weeks` for training and the next `test_weeks` for test.
    """
    dates = unique_sorted_dates(scan_dates)
    if len(dates) < train_weeks + test_weeks:
        return []

    step = step_weeks if step_weeks is not None else test_weeks
    folds: list[WalkForwardFold] = []
    start = 0
    while start + train_weeks + test_weeks <= len(dates):
        train_slice = dates[start : start + train_weeks]
        test_slice = dates[start + train_weeks : start + train_weeks + test_weeks]
        folds.append(
            WalkForwardFold(
                split_date=test_slice[0],
                train_dates=tuple(train_slice),
                test_dates=tuple(test_slice),
            )
        )
        start += step
    return folds


def mask_by_dates(meta: pd.DataFrame, dates: list[date] | tuple[date, ...]) -> pd.Series:
    """Boolean mask where meta['scan_date'] is in dates."""
    date_strs = {str(d) for d in dates}
    return meta["scan_date"].astype(str).isin(date_strs)
