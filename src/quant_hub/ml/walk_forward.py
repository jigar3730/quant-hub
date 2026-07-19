"""Walk-forward date splits for ML training and evaluation (no random shuffle)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

# Spec: discard same-ticker samples in (T, T+5] trading days after a kept signal.
MIN_SIGNAL_EMBARGO_TRADING_DAYS = 5


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


def embargo_calendar_days(horizon_days: int) -> int:
    """Convert trading-session horizon to calendar days (5/7 week approximation).

    Always applies at least MIN_SIGNAL_EMBARGO_TRADING_DAYS when horizon > 0.
    """
    if horizon_days <= 0:
        return 0
    effective = max(int(horizon_days), MIN_SIGNAL_EMBARGO_TRADING_DAYS)
    return int(math.ceil(effective * 7 / 5))


def purge_train_dates(
    train_dates: list[date] | tuple[date, ...],
    *,
    test_start: date,
    horizon_days: int,
) -> list[date]:
    """
    Drop train anchors whose forward label path can overlap the test window.

    A sample labeled with `horizon_days` trading sessions after scan_date D is
    purged when D + embargo_calendar_days(horizon) >= test_start.
    """
    gap = embargo_calendar_days(horizon_days)
    if gap <= 0:
        return list(train_dates)
    cutoff = test_start - timedelta(days=gap)
    return [d for d in train_dates if d < cutoff]


def apply_ticker_signal_embargo(
    frame: pd.DataFrame,
    *,
    ticker_col: str = "ticker",
    date_col: str = "scan_date",
    embargo_trading_days: int = MIN_SIGNAL_EMBARGO_TRADING_DAYS,
) -> pd.DataFrame:
    """
    Per-ticker chronological embargo: after keeping a row at day T, drop later
    rows for the same ticker whose scan_date falls within the next
    `embargo_trading_days` trading sessions (inclusive of T+1 … T+N).
    """
    if frame.empty or ticker_col not in frame.columns or date_col not in frame.columns:
        return frame
    if embargo_trading_days <= 0:
        return frame

    work = frame.copy()
    work["_embargo_date"] = pd.to_datetime(work[date_col]).dt.normalize()
    keep_idx: list[object] = []
    embargo_end_by_ticker: dict[str, pd.Timestamp] = {}

    for idx, row in work.sort_values([ticker_col, "_embargo_date"]).iterrows():
        ticker = str(row[ticker_col])
        scan_ts = row["_embargo_date"]
        if pd.isna(scan_ts):
            continue
        blocked_until = embargo_end_by_ticker.get(ticker)
        if blocked_until is not None and scan_ts <= blocked_until:
            continue
        keep_idx.append(idx)
        # Business-day window: T + N trading days (exclude weekends/holidays approx).
        embargo_end_by_ticker[ticker] = scan_ts + pd.tseries.offsets.BDay(embargo_trading_days)

    out = work.loc[keep_idx].drop(columns=["_embargo_date"])
    return out.sort_index()


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
