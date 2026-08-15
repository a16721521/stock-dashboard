"""Scan staleness decisions + a lightweight background refresh timer.

Holidays are not modelled; at worst a scan runs on a market holiday, which is
harmless. Daily bars only settle after the US cash close (16:00 ET)."""

import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
CLOSE_HOUR = 16


def most_recent_close(now):
    """Datetime of the last weekday 16:00 ET at or before `now`."""
    now = now.astimezone(ET)
    candidate = now.replace(hour=CLOSE_HOUR, minute=0, second=0, microsecond=0)
    if now < candidate:                 # before today's close → step back a day
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:     # Sat=5, Sun=6 → walk back to Friday
        candidate -= timedelta(days=1)
    return candidate


def is_stale(scanned_at, now=None):
    """True if there's no scan or it predates the most recent close."""
    if now is None:
        now = datetime.now(ET)
    if not scanned_at:
        return True
    scanned = datetime.fromisoformat(scanned_at)
    return scanned < most_recent_close(now)


def start_background_timer(run_scan_callback, get_scanned_at, interval_seconds=1800):
    """Every `interval_seconds`, run the scan if stale. Returns the Timer thread.

    run_scan_callback(): performs a scan and writes the cache.
    get_scanned_at(): returns the current cache's scanned_at (or None).
    """
    def _tick():
        try:
            if is_stale(get_scanned_at()):
                run_scan_callback()
        finally:
            timer = threading.Timer(interval_seconds, _tick)
            timer.daemon = True
            timer.start()

    timer = threading.Timer(interval_seconds, _tick)
    timer.daemon = True
    timer.start()
    return timer
