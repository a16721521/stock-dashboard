"""Marketwide scan + hardened on-disk cache (schema v2).

Guarantees:
- A scan is judged on two separate axes that must not be conflated:
    * row coverage  — did we successfully fetch & compute each symbol at all
      (status: complete/partial/rejected/failed; gates whether we commit).
    * date coverage — of the symbols we DID fetch, how many landed on the
      expected finalized session (used to detect uniformly-stale-but-complete
      scans and to drive rescans via needs_scan(); does NOT by itself block a
      commit — a scan where every symbol consistently reports yesterday's bar
      is real, valid data, just old, and should be shown as such rather than
      refused outright).
- Writes are atomic (temp file + os.replace). A rejected or failed scan never
  overwrites the last known-good cache.
- The cache records normalized calculation/ranking/universe hashes so
  incompatible configuration (e.g. a changed lookback) can be detected instead
  of silently reusing stale calculations.
- Every attempt (committed or not) can be persisted separately via
  save_attempt(), so a failed refresh remains visible even though it never
  touches the good cache.
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

# Row-coverage (fetch success) tiers gate whether a scan commits at all.
COMPLETE_COVERAGE_RATIO = 0.98
PARTIAL_COVERAGE_RATIO = 0.90

# Default bar-date freshness floor used by needs_scan() to decide whether the
# scheduler should keep retrying.
DEFAULT_MIN_EXPECTED_DATE_COVERAGE = 0.98


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _normalize(obj):
    """Recursively coerce numbers to float and sort dict keys, so semantically
    identical settings (e.g. 30 vs 30.0) hash identically."""
    if isinstance(obj, dict):
        return {k: _normalize(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return [_normalize(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, float)):
        return float(obj)
    return obj


def _hash(obj):
    canonical = json.dumps(_normalize(obj), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def calculation_hash(lookback, algorithm_version=ALGORITHM_VERSION):
    """Inputs that change the computed indicator VALUES. A mismatch means the
    cached rows were computed under different math and must be rescanned."""
    return _hash({
        "lookback": lookback,
        "algorithm_version": algorithm_version,
        "rsi_period": 14, "wr_period": 14,
        "stoch_k_period": 14, "stoch_d_period": 3, "stoch_smooth_k": 3,
    })


def ranking_hash(thresholds):
    """Inputs that only affect how already-cached rows are RE-RANKED, not their
    values. Deliberately excludes Stochastic thresholds: Stochastic is a chart
    overlay only and is not a ranking factor (see backend.ranking)."""
    return _hash({
        "wr_oversold": thresholds["wr_oversold"], "wr_overbought": thresholds["wr_overbought"],
        "rsi_oversold": thresholds["rsi_oversold"], "rsi_overbought": thresholds["rsi_overbought"],
    })


def settings_hash(settings):
    """Whole-settings hash for display/diagnostics; normalized. Not used to
    gate anything — calculation_hash and ranking_hash serve that purpose."""
    return _hash(settings)


def universe_hash(tickers):
    canonical = json.dumps(sorted(tickers), separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def run_scan(tickers, period, batch_fetcher):
    """Compute raw readings. Returns {rows, coverage, latest_bar_date, errors}.
    Never raises on empty data. Each row carries its own bar_date (P1-2: a
    single cache-level max must not stand in for per-symbol freshness)."""
    tickers = list(tickers)
    try:
        frames = batch_fetcher(tickers, period) or {}
    except Exception as exc:  # a broken fetch must not crash the scan
        return {"rows": [], "errors": [f"fetch failed: {exc}"],
                "latest_bar_date": None,
                "coverage": _coverage(len(tickers), 0, 0, list(tickers))}

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
        bar_date = ind.index[-1].date().isoformat()
        rows.append({
            "ticker": ticker,
            "price": round(float(last["Close"]), 2),
            "wr": round(float(last["WilliamsR"]), 1),
            "rsi": round(float(last["RSI"]), 1),
            "stochK": round(float(last["StochK"]), 1),
            "bar_date": bar_date,
        })
        if latest_bar is None or bar_date > latest_bar:
            latest_bar = bar_date

    valid_syms = {r["ticker"] for r in rows}
    missing_syms = [t for t in tickers if t not in valid_syms]
    return {"rows": rows, "errors": [], "latest_bar_date": latest_bar,
            "coverage": _coverage(len(tickers), len(frames), len(rows), missing_syms)}


def _coverage(requested, downloaded, valid, missing_symbols=None):
    return {"requested": requested, "downloaded": downloaded, "valid": valid,
            "missing": requested - valid,
            "ratio": (valid / requested) if requested else 0.0,
            "missing_symbols": missing_symbols or []}


def compute_date_coverage(rows, expected_date):
    """What fraction of the successfully-fetched rows actually landed on the
    expected finalized session, vs. older/newer. Unknown expected_date (the
    calendar couldn't resolve one) does not penalize — ratio 1.0."""
    if not expected_date:
        return {"expected_date": expected_date,
                "expected_date_count": sum(1 for r in rows if r.get("bar_date") == expected_date),
                "older_date_count": 0, "newer_date_count": 0, "expected_date_ratio": 1.0}
    total = len(rows)
    expected_count = sum(1 for r in rows if r.get("bar_date") == expected_date)
    older = sum(1 for r in rows if r.get("bar_date") and r["bar_date"] < expected_date)
    newer = sum(1 for r in rows if r.get("bar_date") and r["bar_date"] > expected_date)
    ratio = (expected_count / total) if total else 0.0
    return {"expected_date": expected_date, "expected_date_count": expected_count,
            "older_date_count": older, "newer_date_count": newer,
            "expected_date_ratio": ratio}


def _classify_status(coverage):
    """Row-coverage tiers only (fetch success). Bar-date freshness is a
    separate concern surfaced via bar_status/date_coverage, not this status."""
    if coverage["valid"] == 0:
        return "failed"
    ratio = coverage["ratio"]
    if ratio >= COMPLETE_COVERAGE_RATIO:
        return "complete"
    if ratio >= PARTIAL_COVERAGE_RATIO:
        return "partial"
    return "rejected"


def build_cache_payload(scan_result, *, lookback, universe_id, universe_hash,
                        calculation_hash, ranking_hash=None, expected_session_date=None,
                        started_at=None, completed_at=None):
    cov = scan_result["coverage"]
    date_cov = compute_date_coverage(scan_result["rows"], expected_session_date)
    status = _classify_status(cov)
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "calculation_hash": calculation_hash,
        "ranking_hash": ranking_hash,
        "universe_id": universe_id,
        "universe_hash": universe_hash,
        "lookback": lookback,
        "started_at": started_at or _now_iso(),
        "completed_at": completed_at or _now_iso(),
        "expected_session_date": expected_session_date,
        "latest_bar_date": scan_result["latest_bar_date"],
        "status": status,
        "coverage": cov,
        "date_coverage": date_cov,
        "errors": scan_result["errors"],
        "rows": scan_result["rows"],
        # kept for compatibility with older readers
        "scanned_at": completed_at or _now_iso(),
    }


def save_cache_atomic(path, payload):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)   # atomic within a filesystem


def commit_scan(path, payload):
    """Replace the cache only if row coverage is at least "partial" (>=90%).
    A rejected (too little fetched) or failed (nothing fetched) scan preserves
    the existing last-known-good cache untouched.

    Returns {committed: bool, reason: str}.
    """
    status = payload["status"]
    if status in ("failed", "rejected"):
        return {"committed": False, "reason": status}
    save_cache_atomic(path, payload)
    return {"committed": True, "reason": "ok"}


def save_attempt(path, payload, outcome):
    """Persist a record of this scan attempt regardless of whether it
    committed, so a failed/rejected refresh remains visible (P1-3). Row data
    is stripped — this is a diagnostic summary, not a data source."""
    record = {k: v for k, v in payload.items() if k != "rows"}
    record["commit_outcome"] = outcome
    save_cache_atomic(path, record)


def load_cache(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def needs_scan(cache, expected_session_date, calculation_hash_value, universe_hash_value,
              minimum_expected_date_coverage=DEFAULT_MIN_EXPECTED_DATE_COVERAGE):
    """Single source of truth for "should we scan again", replacing the old
    fetch-timestamp-only is_stale(). True whenever the cache is missing,
    computed under different inputs, or doesn't yet contain the expected
    finalized session for enough symbols (the P1-1 case: 100% row coverage but
    every bar is a day behind is NOT considered fresh)."""
    if cache is None:
        return True
    if cache.get("calculation_hash") != calculation_hash_value:
        return True
    if cache.get("universe_hash") != universe_hash_value:
        return True
    date_cov = cache.get("date_coverage") or {}
    if expected_session_date and date_cov.get("expected_date") != expected_session_date:
        return True
    if date_cov.get("expected_date_ratio", 0.0) < minimum_expected_date_coverage:
        return True
    return False
