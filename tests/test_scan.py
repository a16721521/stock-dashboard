import json

import numpy as np
import pandas as pd

from backend.scan import (
    run_scan, build_cache_payload, commit_scan, save_cache_atomic, load_cache,
    save_attempt, needs_scan, calculation_hash, ranking_hash, universe_hash,
    compute_date_coverage, COMPLETE_COVERAGE_RATIO, PARTIAL_COVERAGE_RATIO,
)


def _trend_df(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    down = max(1, int(n * 2 / 3))
    close = np.concatenate([np.linspace(100, 60, down), np.linspace(60, 75, n - down)])
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                         "Close": close, "Volume": np.full(n, 1)}, index=idx)


def _fetcher(mapping):
    return lambda tickers, period: {t: mapping[t] for t in tickers if t in mapping}


def _payload(scan_result, **kw):
    defaults = dict(lookback="6mo", universe_id="u", universe_hash="uh",
                    calculation_hash="ch", ranking_hash="rh")
    defaults.update(kw)
    return build_cache_payload(scan_result, **defaults)


LAST_BAR = _trend_df().index[-1].date().isoformat()


# ---------------------------------------------------------------------------
# run_scan: per-row bar_date (P1-2)
# ---------------------------------------------------------------------------

def test_run_scan_stores_bar_date_per_row():
    fetched = {"AAA": _trend_df(), "BBB": _trend_df()}
    res = run_scan(["AAA", "BBB"], "6mo", _fetcher(fetched))
    for r in res["rows"]:
        assert r["bar_date"] == LAST_BAR


def test_run_scan_survives_fetch_exception():
    def boom(t, p):
        raise RuntimeError("yahoo down")
    res = run_scan(["AAA"], "6mo", boom)
    assert res["rows"] == [] and res["coverage"]["valid"] == 0
    assert res["errors"]


def test_run_scan_missing_symbols_tracked():
    fetched = {"AAA": _trend_df(), "SHORT": _trend_df(10)}
    res = run_scan(["AAA", "SHORT"], "6mo", _fetcher(fetched))
    assert res["coverage"]["missing_symbols"] == ["SHORT"]


# ---------------------------------------------------------------------------
# date_coverage: one current ticker must not mask many stale ones (P1-2)
# ---------------------------------------------------------------------------

def test_date_coverage_flags_mixed_freshness():
    rows = [
        {"ticker": "A", "bar_date": "2026-08-14"},
        {"ticker": "B", "bar_date": "2026-08-13"},
    ]
    dc = compute_date_coverage(rows, "2026-08-14")
    assert dc == {"expected_date": "2026-08-14", "expected_date_count": 1,
                 "older_date_count": 1, "newer_date_count": 0,
                 "expected_date_ratio": 0.5}


def test_date_coverage_all_current():
    rows = [{"ticker": "A", "bar_date": "2026-08-14"},
           {"ticker": "B", "bar_date": "2026-08-14"}]
    dc = compute_date_coverage(rows, "2026-08-14")
    assert dc["expected_date_ratio"] == 1.0


def test_date_coverage_unknown_expected_does_not_penalize():
    rows = [{"ticker": "A", "bar_date": "2026-08-14"}]
    dc = compute_date_coverage(rows, None)
    assert dc["expected_date_ratio"] == 1.0


def test_date_coverage_empty_rows():
    dc = compute_date_coverage([], "2026-08-14")
    assert dc["expected_date_ratio"] == 0.0


# ---------------------------------------------------------------------------
# Hash normalization (P1-4): int vs float thresholds must hash identically
# ---------------------------------------------------------------------------

def test_ranking_hash_normalizes_int_vs_float():
    int_t = {"wr_oversold": -80, "wr_overbought": -20, "rsi_oversold": 30, "rsi_overbought": 70}
    float_t = {k: float(v) for k, v in int_t.items()}
    assert ranking_hash(int_t) == ranking_hash(float_t)


def test_ranking_hash_excludes_stochastic():
    # Stochastic is chart-only, not a ranking factor (P2-3) -> must not affect the hash.
    base = {"wr_oversold": -80, "wr_overbought": -20, "rsi_oversold": 30, "rsi_overbought": 70,
           "stoch_oversold": 20, "stoch_overbought": 80}
    changed = {**base, "stoch_oversold": 5, "stoch_overbought": 95}
    assert ranking_hash(base) == ranking_hash(changed)


def test_ranking_hash_changes_with_wr_or_rsi():
    base = {"wr_oversold": -80, "wr_overbought": -20, "rsi_oversold": 30, "rsi_overbought": 70}
    changed = {**base, "rsi_oversold": 25}
    assert ranking_hash(base) != ranking_hash(changed)


def test_calculation_hash_changes_with_lookback():
    assert calculation_hash("6mo") != calculation_hash("1y")


def test_calculation_hash_stable_for_same_lookback():
    assert calculation_hash("6mo") == calculation_hash("6mo")


def test_universe_hash_order_independent():
    assert universe_hash(["A", "B"]) == universe_hash(["B", "A"])


# ---------------------------------------------------------------------------
# Status tiers (P2-2): complete >=98%, partial >=90%, rejected <90%
# ---------------------------------------------------------------------------

def _mapping(n_valid, n_total):
    m = {f"S{i}": _trend_df() for i in range(n_valid)}
    tickers = [f"S{i}" for i in range(n_total)]
    return tickers, m


def test_status_complete_at_98_percent():
    tickers, m = _mapping(98, 100)
    res = run_scan(tickers, "6mo", _fetcher(m))
    payload = _payload(res)
    assert payload["coverage"]["ratio"] == 0.98
    assert payload["status"] == "complete"


def test_status_partial_between_90_and_98_percent():
    tickers, m = _mapping(93, 100)
    res = run_scan(tickers, "6mo", _fetcher(m))
    payload = _payload(res)
    assert payload["status"] == "partial"


def test_status_rejected_below_90_percent():
    tickers, m = _mapping(80, 100)
    res = run_scan(tickers, "6mo", _fetcher(m))
    payload = _payload(res)
    assert payload["status"] == "rejected"


def test_status_failed_on_zero_rows():
    res = run_scan(["A", "B"], "6mo", _fetcher({}))
    payload = _payload(res)
    assert payload["status"] == "failed"


# ---------------------------------------------------------------------------
# commit_scan: only complete/partial commit; rejected/failed never overwrite
# good cache (this directly targets the P2-2 finding: a 260/518 partial scan
# must not silently replace a previous complete 518/518 scan)
# ---------------------------------------------------------------------------

def test_complete_scan_commits(tmp_path):
    p = tmp_path / "scan_cache.json"
    tickers, m = _mapping(100, 100)
    payload = _payload(run_scan(tickers, "6mo", _fetcher(m)))
    assert commit_scan(p, payload) == {"committed": True, "reason": "ok"}
    assert load_cache(p)["status"] == "complete"


def test_partial_scan_commits_with_warning_status(tmp_path):
    p = tmp_path / "scan_cache.json"
    tickers, m = _mapping(92, 100)
    payload = _payload(run_scan(tickers, "6mo", _fetcher(m)))
    assert commit_scan(p, payload) == {"committed": True, "reason": "ok"}
    assert load_cache(p)["status"] == "partial"


def test_rejected_scan_does_not_replace_good_cache(tmp_path):
    p = tmp_path / "scan_cache.json"
    good_tickers, good_m = _mapping(100, 100)
    good = _payload(run_scan(good_tickers, "6mo", _fetcher(good_m)))
    commit_scan(p, good)

    bad_tickers, bad_m = _mapping(50, 100)   # 50% -> below 90% reject floor
    bad = _payload(run_scan(bad_tickers, "6mo", _fetcher(bad_m)))
    res = commit_scan(p, bad)
    assert res == {"committed": False, "reason": "rejected"}
    assert load_cache(p)["coverage"]["valid"] == 100   # good cache untouched


def test_zero_row_scan_does_not_replace_good_cache(tmp_path):
    p = tmp_path / "scan_cache.json"
    good = _payload(run_scan(["A", "B"], "6mo", _fetcher({"A": _trend_df(), "B": _trend_df()})))
    commit_scan(p, good)
    empty = _payload(run_scan(["A", "B"], "6mo", _fetcher({})))
    res = commit_scan(p, empty)
    assert res == {"committed": False, "reason": "failed"}
    assert len(load_cache(p)["rows"]) == 2


def test_commit_is_atomic_no_leftover_tmp(tmp_path):
    p = tmp_path / "scan_cache.json"
    payload = _payload(run_scan(["A"], "6mo", _fetcher({"A": _trend_df()})))
    commit_scan(p, payload)
    assert not (tmp_path / "scan_cache.json.tmp").exists()


# ---------------------------------------------------------------------------
# needs_scan (P1-1): the exact scenario the review demonstrated — a scan
# that's 100% row-coverage but uniformly one day stale must trigger a rescan.
# ---------------------------------------------------------------------------

def _cache_with(status="complete", calc_hash="ch1", uni_hash="uh1",
               expected_date="2026-08-14", ratio=1.0):
    return {
        "status": status, "calculation_hash": calc_hash, "universe_hash": uni_hash,
        "date_coverage": {"expected_date": expected_date, "expected_date_ratio": ratio},
    }


def test_needs_scan_true_when_no_cache():
    assert needs_scan(None, "2026-08-14", "ch1", "uh1") is True


def test_needs_scan_true_on_stale_bar_despite_full_row_coverage():
    # The exact P1-1 case: coverage 100%, but latest bar is a day behind.
    cache = _cache_with(expected_date="2026-08-13", ratio=1.0)  # cache is FOR 08-13
    assert needs_scan(cache, "2026-08-14", "ch1", "uh1") is True


def test_needs_scan_true_on_calculation_hash_mismatch():
    cache = _cache_with(calc_hash="ch_old")
    assert needs_scan(cache, "2026-08-14", "ch_new", "uh1") is True


def test_needs_scan_true_on_universe_hash_mismatch():
    cache = _cache_with(uni_hash="uh_old")
    assert needs_scan(cache, "2026-08-14", "ch1", "uh_new") is True


def test_needs_scan_true_on_low_date_ratio():
    cache = _cache_with(expected_date="2026-08-14", ratio=0.5)
    assert needs_scan(cache, "2026-08-14", "ch1", "uh1") is True


def test_needs_scan_false_when_fully_current_and_compatible():
    cache = _cache_with(expected_date="2026-08-14", ratio=1.0)
    assert needs_scan(cache, "2026-08-14", "ch1", "uh1") is False


def test_needs_scan_respects_custom_threshold():
    cache = _cache_with(expected_date="2026-08-14", ratio=0.95)
    assert needs_scan(cache, "2026-08-14", "ch1", "uh1",
                      minimum_expected_date_coverage=0.99) is True
    assert needs_scan(cache, "2026-08-14", "ch1", "uh1",
                      minimum_expected_date_coverage=0.90) is False


# ---------------------------------------------------------------------------
# Last-attempt persistence (P1-3): a failed refresh must be recorded and
# visible even though it never touches the good cache.
# ---------------------------------------------------------------------------

def test_save_attempt_records_outcome_and_strips_rows(tmp_path):
    p = tmp_path / "scan_last_attempt.json"
    payload = _payload(run_scan(["A"], "6mo", _fetcher({})))  # zero rows -> failed
    outcome = {"committed": False, "reason": "failed"}
    save_attempt(p, payload, outcome)
    attempt = load_cache(p)
    assert attempt["commit_outcome"] == outcome
    assert attempt["status"] == "failed"
    assert "rows" not in attempt


def test_save_attempt_atomic(tmp_path):
    p = tmp_path / "scan_last_attempt.json"
    payload = _payload(run_scan(["A"], "6mo", _fetcher({"A": _trend_df()})))
    save_attempt(p, payload, {"committed": True, "reason": "ok"})
    assert not (tmp_path / "scan_last_attempt.json.tmp").exists()


# ---------------------------------------------------------------------------
# Basic cache I/O
# ---------------------------------------------------------------------------

def test_load_cache_missing_returns_none(tmp_path):
    assert load_cache(tmp_path / "nope.json") is None


def test_load_cache_corrupt_returns_none(tmp_path):
    p = tmp_path / "scan_cache.json"
    p.write_text("{not json")
    assert load_cache(p) is None


def test_schema_version_present(tmp_path):
    payload = _payload(run_scan(["A"], "6mo", _fetcher({"A": _trend_df()})))
    assert payload["schema_version"] == 2
