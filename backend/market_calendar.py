"""Authoritative NYSE session calendar for data-freshness decisions.

Handles weekends, holidays, early closes, and DST via pandas_market_calendars,
plus a configurable post-close settlement delay before a session's daily bar is
treated as final.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

ET = ZoneInfo("America/New_York")
_NYSE = mcal.get_calendar("XNYS")
SETTLE_DELAY_MINUTES = 20


def _sessions(now_et):
    """(date, open_et, close_et) ascending for ~2 weeks up to now_et."""
    end = now_et.date()
    start = end - timedelta(days=15)
    sched = _NYSE.schedule(start_date=start.isoformat(), end_date=end.isoformat())
    out = []
    for idx, row in sched.iterrows():
        open_et = row["market_open"].tz_convert(ET).to_pydatetime()
        close_et = row["market_close"].tz_convert(ET).to_pydatetime()
        out.append((idx.date(), open_et, close_et))
    return out


def _now_et(now):
    return (now or datetime.now(ET)).astimezone(ET)


def expected_session_date(now=None, settle_delay_minutes=SETTLE_DELAY_MINUTES):
    """ISO date of the most recent session already closed (close + settle <= now)."""
    now = _now_et(now)
    for date, _open, close in reversed(_sessions(now)):
        if close + timedelta(minutes=settle_delay_minutes) <= now:
            return date.isoformat()
    return None


def current_session_date(now=None):
    """ISO date if a regular session is in progress right now, else None."""
    now = _now_et(now)
    for date, open_et, close_et in _sessions(now):
        if date == now.date() and open_et <= now <= close_et:
            return date.isoformat()
    return None


def bar_status(latest_bar_date, now=None, settle_delay_minutes=SETTLE_DELAY_MINUTES):
    """Classify a daily bar's freshness: final / provisional / stale / unknown."""
    if not latest_bar_date:
        return "unknown"
    now = _now_et(now)
    current = current_session_date(now)
    if current and latest_bar_date == current:
        return "provisional"           # today's bar, session still open
    expected = expected_session_date(now, settle_delay_minutes)
    if expected is None:
        return "unknown"
    if latest_bar_date == expected:
        return "final"
    if latest_bar_date < expected:
        return "stale"
    return "provisional"               # bar ahead of last closed session
