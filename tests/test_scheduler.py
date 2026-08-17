"""Tests for the generic timer only. Freshness/staleness decisions are
covered by backend.scan.needs_scan tests in tests/test_scan.py — this module
has no calendar knowledge of its own (see scheduler.py docstring)."""

import threading

from backend.scheduler import start_background_timer


def test_start_background_timer_returns_a_timer():
    timer = start_background_timer(
        run_scan_callback=lambda: None,
        needs_scan_fn=lambda: False,
        interval_seconds=3600,
    )
    try:
        assert isinstance(timer, threading.Timer)
        assert timer.is_alive()
    finally:
        timer.cancel()


def test_timer_does_not_fire_before_its_interval():
    calls = []
    timer = start_background_timer(
        run_scan_callback=lambda: calls.append(1),
        needs_scan_fn=lambda: True,
        interval_seconds=3600,
    )
    try:
        assert calls == []   # nothing fires within the test's lifetime
    finally:
        timer.cancel()
