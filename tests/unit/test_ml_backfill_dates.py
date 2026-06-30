"""Unit tests for ML backfill date helpers."""

from datetime import date

import pandas as pd

from quant_hub.ml.backfill_dates import (
    as_scan_date,
    compute_backfill_coverage,
    iter_weekly_scan_dates,
    truncate_weekly_to_date,
)


def test_iter_weekly_scan_dates_fridays():
    dates = iter_weekly_scan_dates(date(2024, 1, 1), date(2024, 1, 31))
    assert dates == [
        date(2024, 1, 5),
        date(2024, 1, 12),
        date(2024, 1, 19),
        date(2024, 1, 26),
    ]


def test_iter_weekly_scan_dates_empty_when_since_after_until():
    assert iter_weekly_scan_dates(date(2024, 6, 1), date(2024, 5, 1)) == []


def test_truncate_weekly_to_date_no_lookahead():
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-05", "2024-01-12", "2024-01-19"]),
            "Close": [100.0, 101.0, 102.0],
        }
    )
    out = truncate_weekly_to_date(df, date(2024, 1, 12))
    assert len(out) == 2
    assert out["Close"].iloc[-1] == 101.0


def test_truncate_weekly_empty_when_before_first_bar():
    df = pd.DataFrame(
        {"Date": pd.to_datetime(["2024-06-07"]), "Close": [50.0]},
    )
    out = truncate_weekly_to_date(df, date(2024, 1, 1))
    assert out is not None
    assert out.empty


def test_compute_backfill_coverage_missing_dates():
    coverage = compute_backfill_coverage(
        since=date(2020, 1, 1),
        until=date(2020, 1, 31),
        existing_dates={date(2020, 1, 10)},
    )
    assert coverage.planned_dates == [
        date(2020, 1, 3),
        date(2020, 1, 10),
        date(2020, 1, 17),
        date(2020, 1, 24),
        date(2020, 1, 31),
    ]
    assert coverage.missing_dates == [
        date(2020, 1, 3),
        date(2020, 1, 17),
        date(2020, 1, 24),
        date(2020, 1, 31),
    ]


def test_as_scan_date_normalizes_datetime():
    from datetime import datetime

    assert as_scan_date(datetime(2020, 1, 3, 12, 0)) == date(2020, 1, 3)
    assert as_scan_date("2020-01-03") == date(2020, 1, 3)
