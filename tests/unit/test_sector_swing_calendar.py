from __future__ import annotations

from datetime import date, datetime

import pytest

from quant_hub.sector_swing.calendar import (
    ET,
    expected_last_session,
    is_trading_day,
    previous_trading_day,
)


def et(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=ET)


@pytest.mark.parametrize(
    "now, expected",
    [
        (et(2026, 9, 21, 5, 20), date(2026, 9, 18)),  # Mon premarket -> prior Friday
        (et(2026, 9, 22, 5, 20), date(2026, 9, 21)),  # Tue premarket -> Monday
        (et(2026, 9, 18, 16, 14), date(2026, 9, 17)),  # before the 16:15 cutoff -> prior day
        (et(2026, 9, 18, 16, 15), date(2026, 9, 18)),  # at cutoff -> today
        (et(2026, 9, 19, 12, 0), date(2026, 9, 18)),  # Saturday -> Friday
        (et(2026, 9, 20, 23, 0), date(2026, 9, 18)),  # Sunday -> Friday
        (et(2026, 9, 8, 5, 20), date(2026, 9, 4)),  # Tue after Labor Day (Mon 9/7) -> Fri 9/4
        (et(2026, 9, 7, 18, 0), date(2026, 9, 4)),  # holiday evening -> still Fri 9/4
        (et(2026, 4, 6, 5, 20), date(2026, 4, 2)),  # Mon after Good Friday (4/3) -> Thu 4/2
    ],
)
def test_expected_last_session(now, expected):
    assert expected_last_session(now) == expected


def test_naive_datetime_is_treated_as_eastern():
    assert expected_last_session(datetime(2026, 9, 21, 5, 20)) == date(2026, 9, 18)


def test_utc_input_is_converted_to_eastern():
    from datetime import UTC

    # 09:20 UTC on Mon 9/21 is 05:20 ET.
    assert expected_last_session(datetime(2026, 9, 21, 9, 20, tzinfo=UTC)) == date(2026, 9, 18)


def test_previous_trading_day_skips_weekend_and_holiday():
    assert previous_trading_day(date(2026, 9, 8)) == date(2026, 9, 4)
    assert not is_trading_day(date(2026, 12, 25))
    assert is_trading_day(date(2026, 12, 24))


def test_unknown_year_falls_back_to_weekdays(caplog):
    assert is_trading_day(date(2035, 7, 4))  # no holiday list -> weekday only
    assert not is_trading_day(date(2035, 7, 7))  # Saturday
