"""Colombian public-holiday helpers.

The restaurant only uses this to allow weekend specials on Monday holidays.
Rules are calculated locally so the bot does not depend on a third-party API at
ordering time.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def is_colombian_monday_holiday(value: date) -> bool:
    return value.weekday() == 0 and value in colombian_public_holidays(value.year)


@lru_cache(maxsize=64)
def colombian_public_holidays(year: int) -> frozenset[date]:
    easter = _easter_sunday(year)
    holidays = {
        date(year, 1, 1),
        date(year, 5, 1),
        date(year, 7, 20),
        date(year, 8, 7),
        date(year, 12, 8),
        date(year, 12, 25),
        _next_or_same_monday(date(year, 1, 6)),
        _next_or_same_monday(date(year, 3, 19)),
        easter - timedelta(days=3),
        easter - timedelta(days=2),
        easter + timedelta(days=43),
        easter + timedelta(days=64),
        easter + timedelta(days=71),
        _next_or_same_monday(date(year, 6, 29)),
        _next_or_same_monday(date(year, 8, 15)),
        _next_or_same_monday(date(year, 10, 12)),
        _next_or_same_monday(date(year, 11, 1)),
        _next_or_same_monday(date(year, 11, 11)),
    }
    if year >= 2026:
        holidays.add(_next_or_same_monday(date(year, 7, 9)))
    return frozenset(holidays)


def _next_or_same_monday(value: date) -> date:
    return value + timedelta(days=(7 - value.weekday()) % 7)


def _easter_sunday(year: int) -> date:
    # Anonymous Gregorian algorithm, valid for the Gregorian calendar.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)
