"""NYSE session calendar: the last completed session, for price-cache freshness checks.

Hard-coded holiday list (no new dependency). Years outside ``_HOLIDAYS`` degrade to
weekday-only logic and log a warning.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# NYSE closes 16:00 ET; allow 15 min for the final daily bar to settle at the vendor.
SESSION_CLOSE_HOUR = 16
SESSION_CLOSE_MINUTE = 15

ET = ZoneInfo("America/New_York")

_HOLIDAYS: dict[int, frozenset[date]] = {
    2025: frozenset(
        {
            date(2025, 1, 1),
            date(2025, 1, 9),  # National Day of Mourning (President Carter)
            date(2025, 1, 20),
            date(2025, 2, 17),
            date(2025, 4, 18),
            date(2025, 5, 26),
            date(2025, 6, 19),
            date(2025, 7, 4),
            date(2025, 9, 1),
            date(2025, 11, 27),
            date(2025, 12, 25),
        }
    ),
    2026: frozenset(
        {
            date(2026, 1, 1),
            date(2026, 1, 19),
            date(2026, 2, 16),
            date(2026, 4, 3),
            date(2026, 5, 25),
            date(2026, 6, 19),
            date(2026, 7, 3),  # Independence Day observed
            date(2026, 9, 7),
            date(2026, 11, 26),
            date(2026, 12, 25),
        }
    ),
    2027: frozenset(
        {
            date(2027, 1, 1),
            date(2027, 1, 18),
            date(2027, 2, 15),
            date(2027, 3, 26),
            date(2027, 5, 31),
            date(2027, 6, 18),  # Juneteenth observed
            date(2027, 7, 5),  # Independence Day observed
            date(2027, 9, 6),
            date(2027, 11, 25),
            date(2027, 12, 24),  # Christmas observed
        }
    ),
    2028: frozenset(
        {
            date(2028, 1, 17),
            date(2028, 2, 21),
            date(2028, 4, 14),
            date(2028, 5, 29),
            date(2028, 6, 19),
            date(2028, 7, 4),
            date(2028, 9, 4),
            date(2028, 11, 23),
            date(2028, 12, 25),
        }
    ),
}

_warned_years: set[int] = set()


def is_trading_day(day: date) -> bool:
    if day.weekday() >= 5:
        return False
    holidays = _HOLIDAYS.get(day.year)
    if holidays is None:
        if day.year not in _warned_years:
            _warned_years.add(day.year)
            logger.warning(
                "No NYSE holiday list for %d in data/calendar.py; using weekdays only",
                day.year,
            )
        return True
    return day not in holidays


def previous_trading_day(day: date) -> date:
    """Latest trading day strictly before ``day``."""
    candidate = day - timedelta(days=1)
    while not is_trading_day(candidate):
        candidate -= timedelta(days=1)
    return candidate


def expected_last_session(now: datetime | None = None) -> date:
    """Date of the newest fully completed session as of ``now`` (default: current time, ET)."""
    now_et = (now or datetime.now(ET))
    now_et = now_et.astimezone(ET) if now_et.tzinfo else now_et.replace(tzinfo=ET)
    today = now_et.date()
    close = time(SESSION_CLOSE_HOUR, SESSION_CLOSE_MINUTE)
    if is_trading_day(today) and now_et.time() >= close:
        return today
    return previous_trading_day(today)
