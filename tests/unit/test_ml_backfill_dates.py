"""Unit tests for ML backfill date helpers."""

from datetime import date

import pandas as pd

from quant_hub.ml.backfill_dates import (
    as_scan_date,
    compute_backfill_coverage,
    iter_saturday_scan_dates,
    truncate_daily_to_date,
)


def test_iter_saturday_scan_dates():
    dates = iter_saturday_scan_dates(date(2024, 1, 1), date(2024, 1, 31))
    assert dates == [
        date(2024, 1, 6),
        date(2024, 1, 13),
        date(2024, 1, 20),
        date(2024, 1, 27),
    ]


def test_truncate_daily_to_date_no_lookahead():
    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-05", "2024-01-12", "2024-01-19"]),
            "Close": [100.0, 101.0, 102.0],
        }
    )
    out = truncate_daily_to_date(df, date(2024, 1, 12))
    assert len(out) == 2
    assert out["Close"].iloc[-1] == 101.0


def test_truncate_daily_empty_when_before_first_bar():
    df = pd.DataFrame(
        {"Date": pd.to_datetime(["2024-06-07"]), "Close": [50.0]},
    )
    out = truncate_daily_to_date(df, date(2024, 1, 1))
    assert out is not None
    assert out.empty


def test_compute_backfill_coverage_missing_dates():
    coverage = compute_backfill_coverage(
        since=date(2020, 1, 1),
        until=date(2020, 1, 31),
        existing_dates={date(2020, 1, 11)},
    )
    assert coverage.planned_dates == [
        date(2020, 1, 4),
        date(2020, 1, 11),
        date(2020, 1, 18),
        date(2020, 1, 25),
    ]
    assert coverage.missing_dates == [
        date(2020, 1, 4),
        date(2020, 1, 18),
        date(2020, 1, 25),
    ]


def test_as_scan_date_normalizes_datetime():
    from datetime import datetime

    assert as_scan_date(datetime(2020, 1, 3, 12, 0)) == date(2020, 1, 3)
    assert as_scan_date("2020-01-03") == date(2020, 1, 3)
