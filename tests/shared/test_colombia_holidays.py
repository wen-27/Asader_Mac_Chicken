"""Automated test module. It protects local holiday calculations used by stock rules."""

from __future__ import annotations

from datetime import date

from app.shared.utils.colombia_holidays import colombian_public_holidays, is_colombian_monday_holiday


def test_colombian_public_holidays_include_2026_chiquinquira_monday() -> None:
    assert date(2026, 7, 13) in colombian_public_holidays(2026)
    assert is_colombian_monday_holiday(date(2026, 7, 13))


def test_colombian_public_holidays_include_common_monday_holidays() -> None:
    assert is_colombian_monday_holiday(date(2026, 1, 12))
    assert is_colombian_monday_holiday(date(2026, 6, 8))
    assert is_colombian_monday_holiday(date(2026, 6, 15))
    assert is_colombian_monday_holiday(date(2026, 11, 16))


def test_non_monday_public_holiday_does_not_enable_monday_specials() -> None:
    assert date(2026, 8, 7) in colombian_public_holidays(2026)
    assert not is_colombian_monday_holiday(date(2026, 8, 7))
