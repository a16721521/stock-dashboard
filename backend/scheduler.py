"""Generic recurring-scan timer.

This module deliberately knows nothing about trading sessions or cache
validity — those decisions live in backend.market_calendar (session/bar-date
freshness) and backend.scan.needs_scan (cache compatibility + freshness).
Keeping a single calendar/validity model instead of a second one here is the
fix for a real bug: an earlier version of this module had its own
weekday-only staleness check that a fully-calendar-aware cache could
disagree with, so the scheduler could accept a scan that was actually stale.
"""

import threading


def start_background_timer(run_scan_callback, needs_scan_fn, interval_seconds=1800):
    """Every `interval_seconds`, call run_scan_callback() if needs_scan_fn()
    returns True. Returns the Timer thread (useful for tests/shutdown).

    run_scan_callback(): performs a scan and (if valid) commits it.
    needs_scan_fn(): no-arg predicate — should consult backend.scan.needs_scan
        against the current cache, expected session, and calculation/universe
        hashes.
    """
    def _tick():
        try:
            if needs_scan_fn():
                run_scan_callback()
        finally:
            timer = threading.Timer(interval_seconds, _tick)
            timer.daemon = True
            timer.start()

    timer = threading.Timer(interval_seconds, _tick)
    timer.daemon = True
    timer.start()
    return timer
