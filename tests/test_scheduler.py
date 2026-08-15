from datetime import datetime
from zoneinfo import ZoneInfo

from backend.scheduler import most_recent_close, is_stale

ET = ZoneInfo("America/New_York")


def test_most_recent_close_same_day_after_4pm():
    now = datetime(2026, 8, 14, 17, 0, tzinfo=ET)  # Friday 5pm
    c = most_recent_close(now)
    assert c == datetime(2026, 8, 14, 16, 0, tzinfo=ET)


def test_most_recent_close_before_4pm_uses_prior_weekday():
    now = datetime(2026, 8, 14, 9, 0, tzinfo=ET)  # Friday 9am
    c = most_recent_close(now)
    assert c == datetime(2026, 8, 13, 16, 0, tzinfo=ET)  # Thursday close


def test_most_recent_close_weekend_uses_friday():
    now = datetime(2026, 8, 16, 12, 0, tzinfo=ET)  # Sunday
    c = most_recent_close(now)
    assert c == datetime(2026, 8, 14, 16, 0, tzinfo=ET)  # Friday close


def test_is_stale_true_when_no_scan():
    now = datetime(2026, 8, 14, 17, 0, tzinfo=ET)
    assert is_stale(None, now) is True


def test_is_stale_false_when_scan_after_close():
    now = datetime(2026, 8, 14, 17, 0, tzinfo=ET)
    scanned = datetime(2026, 8, 14, 16, 30, tzinfo=ET).isoformat()
    assert is_stale(scanned, now) is False


def test_is_stale_true_when_scan_before_close():
    now = datetime(2026, 8, 14, 17, 0, tzinfo=ET)
    scanned = datetime(2026, 8, 14, 15, 0, tzinfo=ET).isoformat()  # before today's close
    assert is_stale(scanned, now) is True
