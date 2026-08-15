"""Marketwide scan + hardened on-disk cache (schema v2).

Guarantees:
- A failed or low-coverage scan never overwrites the last known-good cache.
- Writes are atomic (temp file + os.replace).
- The cache records its calculation inputs (lookback, algorithm version,
  settings/universe hashes) and freshness (latest_bar_date), so staleness is
  judged by bar date, not fetch time, and stale inputs can be detected.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from backend.indicators import build_indicator_frame

MIN_ROWS = 20
SCHEMA_VERSION = 2
ALGORITHM_VERSION = "indicators-v2"
MIN_COVERAGE = 0.5


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def settings_hash(settings):
    canonical = json.dumps(settings, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def universe_hash(tickers):
    canonical = json.dumps(sorted(tickers), separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def run_scan(tickers, period, batch_fetcher):
    """Compute raw readings and coverage. Returns
    {rows, coverage, latest_bar_date, errors}. Never raises on empty data."""
    tickers = list(tickers)
    try:
        frames = batch_fetcher(tickers, period) or {}
    except Exception as exc:  # a broken fetch must not crash the scan
        return {"rows": [], "errors": [f"fetch failed: {exc}"],
                "latest_bar_date": None,
                "coverage": _coverage(len(tickers), 0, 0)}

    rows = []
    latest_bar = None
    for ticker in tickers:
        df = frames.get(ticker)
        if df is None or len(df) < MIN_ROWS:
            continue
        ind = build_indicator_frame(df)
        last = ind.iloc[-1]
        if last[["WilliamsR", "RSI", "StochK"]].isna().any():
            continue
        rows.append({
            "ticker": ticker,
            "price": round(float(last["Close"]), 2),
            "wr": round(float(last["WilliamsR"]), 1),
            "rsi": round(float(last["RSI"]), 1),
            "stochK": round(float(last["StochK"]), 1),
        })
        bar_date = ind.index[-1].date().isoformat()
        if latest_bar is None or bar_date > latest_bar:
            latest_bar = bar_date

    return {"rows": rows, "errors": [], "latest_bar_date": latest_bar,
            "coverage": _coverage(len(tickers), len(frames), len(rows))}


def _coverage(requested, downloaded, valid):
    return {"requested": requested, "downloaded": downloaded, "valid": valid,
            "missing": requested - valid,
            "ratio": (valid / requested) if requested else 0.0}


def build_cache_payload(scan_result, *, lookback, universe_id, universe_hash,
                        settings_hash, expected_session_date=None,
                        started_at=None, completed_at=None):
    cov = scan_result["coverage"]
    if cov["valid"] == 0:
        status = "failed"
    elif cov["missing"] > 0:
        status = "partial"
    else:
        status = "complete"
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "settings_hash": settings_hash,
        "universe_id": universe_id,
        "universe_hash": universe_hash,
        "lookback": lookback,
        "started_at": started_at or _now_iso(),
        "completed_at": completed_at or _now_iso(),
        "expected_session_date": expected_session_date,
        "latest_bar_date": scan_result["latest_bar_date"],
        "status": status,
        "coverage": cov,
        "errors": scan_result["errors"],
        "rows": scan_result["rows"],
        # kept for compatibility with existing readers
        "scanned_at": completed_at or _now_iso(),
    }


def save_cache_atomic(path, payload):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)   # atomic within a filesystem


def commit_scan(path, payload, min_coverage=MIN_COVERAGE):
    """Replace the cache only if the new scan is trustworthy. A zero-row or
    below-threshold-coverage scan preserves the existing last-known-good cache.

    Returns {committed: bool, reason: str}.
    """
    cov = payload["coverage"]
    if cov["valid"] == 0:
        return {"committed": False, "reason": "zero_rows"}
    if cov["ratio"] < min_coverage:
        return {"committed": False, "reason": "low_coverage"}
    save_cache_atomic(path, payload)
    return {"committed": True, "reason": "ok"}


def load_cache(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None
