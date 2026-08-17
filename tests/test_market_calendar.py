"""Freshness/calendar tests against real NYSE 2026 data:
- 2026-11-26 Thanksgiving is a holiday (no session)
- 2026-11-27 is an early close (13:00 ET)
- 2026-01-01 New Year is a holiday
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.market_calendar import (
    expected_session_date, current_session_date, bar_status,
)

ET = ZoneInfo("America/New_York")


def _et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


def test_holiday_is_skipped_thanksgiving():
    # Noon on Thanksgiving -> last closed session is Wed 2026-11-25
    assert expected_session_date(_et(2026, 11, 26, 12, 0)) == "2026-11-25"


def test_new_year_holiday_skipped():
    assert expected_session_date(_et(2026, 1, 1, 12, 0)) == "2025-12-31"


def test_early_close_before_close_not_yet_final():
    # 12:30 ET on the half-day 2026-11-27: 27th not closed; 26th holiday -> 25th
    assert expected_session_date(_et(2026, 11, 27, 12, 30)) == "2026-11-25"


def test_early_close_after_close_is_final():
    # 13:30 ET is past the 13:00 early close (+20m settle) -> 27th counts
    assert expected_session_date(_et(2026, 11, 27, 13, 30)) == "2026-11-27"


def test_current_session_during_hours():
    assert current_session_date(_et(2026, 11, 27, 12, 30)) == "2026-11-27"


def test_no_current_session_after_close():
    assert current_session_date(_et(2026, 11, 27, 13, 30)) is None


def test_bar_status_final():
    assert bar_status("2026-11-25", now=_et(2026, 11, 25, 17, 0)) == "final"


def test_bar_status_provisional_during_session():
    assert bar_status("2026-11-27", now=_et(2026, 11, 27, 12, 30)) == "provisional"


def test_bar_status_stale():
    assert bar_status("2026-11-25", now=_et(2026, 11, 30, 17, 0)) == "stale"


def test_bar_status_unknown_when_missing():
    assert bar_status(None, now=_et(2026, 11, 30, 17, 0)) == "unknown"
