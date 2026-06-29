"""Unit tests for walk-forward date splitting."""

from __future__ import annotations

from datetime import date

import pandas as pd

from quant_hub.ml.walk_forward import (
    iter_walk_forward_folds,
    mask_by_dates,
    simple_holdout_split,
    unique_sorted_dates,
)


def _weeks(start: str, n: int) -> list[date]:
    base = date.fromisoformat(start)
    return [date.fromordinal(base.toordinal() + 7 * i) for i in range(n)]


def test_unique_sorted_dates_deduplicates_and_sorts():
    dates = unique_sorted_dates(["2024-03-01", "2024-01-05", "2024-01-05", "2024-02-02"])
    assert dates == [date(2024, 1, 5), date(2024, 2, 2), date(2024, 3, 1)]


def test_simple_holdout_split_no_leakage():
    scan_dates = _weeks("2024-01-05", 10)
    train, test = simple_holdout_split(scan_dates, split_date=date(2024, 3, 1))
    assert all(d < date(2024, 3, 1) for d in train)
    assert all(d >= date(2024, 3, 1) for d in test)
    assert len(train) + len(test) == len(scan_dates)


def test_iter_walk_forward_folds_rolling_windows():
    dates = _weeks("2023-01-06", 70)
    folds = iter_walk_forward_folds(dates, train_weeks=52, test_weeks=13, step_weeks=13)
    assert len(folds) >= 1
    fold = folds[0]
    assert len(fold.train_dates) == 52
    assert len(fold.test_dates) == 13
    assert max(fold.train_dates) < min(fold.test_dates)


def test_iter_walk_forward_insufficient_dates_returns_empty():
    dates = _weeks("2024-01-05", 20)
    assert iter_walk_forward_folds(dates, train_weeks=52, test_weeks=13) == []


def test_mask_by_dates():
    meta = pd.DataFrame({"scan_date": ["2024-01-05", "2024-01-12", "2024-01-19"]})
    mask = mask_by_dates(meta, [date(2024, 1, 5), date(2024, 1, 19)])
    assert mask.tolist() == [True, False, True]
