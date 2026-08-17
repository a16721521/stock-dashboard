import json

import numpy as np
import pandas as pd

from backend.scan import (
    run_scan, build_cache_payload, commit_scan, save_cache_atomic, load_cache,
    settings_hash, universe_hash,
)


def _trend_df(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    down = max(1, int(n * 2 / 3))
    close = np.concatenate([np.linspace(100, 60, down), np.linspace(60, 75, n - down)])
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                         "Close": close, "Volume": np.full(n, 1)}, index=idx)


def _payload(scan_result, **kw):
    defaults = dict(lookback="6mo", universe_id="u", universe_hash="uh",
                    settings_hash="sh")
    defaults.update(kw)
    return build_cache_payload(scan_result, **defaults)


def test_run_scan_reports_rows_coverage_and_bar_date():
    fetched = {"AAA": _trend_df(), "BBB": _trend_df()}
    res = run_scan(["AAA", "BBB"], "6mo", lambda t, p: fetched)
    assert {r["ticker"] for r in res["rows"]} == {"AAA", "BBB"}
    assert res["coverage"] == {"requested": 2, "downloaded": 2, "valid": 2,
                               "missing": 0, "ratio": 1.0, "missing_symbols": []}
    assert res["latest_bar_date"] == _trend_df().index[-1].date().isoformat()


def test_run_scan_skips_short_series_in_coverage():
    fetched = {"AAA": _trend_df(), "SHORT": _trend_df(10)}
    res = run_scan(["AAA", "SHORT"], "6mo", lambda t, p: fetched)
    assert {r["ticker"] for r in res["rows"]} == {"AAA"}
    assert res["coverage"]["valid"] == 1 and res["coverage"]["missing"] == 1
    assert res["coverage"]["missing_symbols"] == ["SHORT"]


def test_run_scan_survives_fetch_exception():
    def boom(t, p):
        raise RuntimeError("yahoo down")
    res = run_scan(["AAA"], "6mo", boom)
    assert res["rows"] == [] and res["coverage"]["valid"] == 0
    assert res["errors"]


def test_empty_scan_does_not_replace_good_cache(tmp_path):
    p = tmp_path / "scan_cache.json"
    good = _payload(run_scan(["AAA", "BBB"], "6mo",
                             lambda t, p_: {"AAA": _trend_df(), "BBB": _trend_df()}))
    assert commit_scan(p, good)["committed"] is True
    # now a failed (empty) scan
    empty = _payload(run_scan(["AAA", "BBB"], "6mo", lambda t, p_: {}))
    res = commit_scan(p, empty)
    assert res["committed"] is False and res["reason"] == "zero_rows"
    # good cache still intact
    assert len(load_cache(p)["rows"]) == 2


def test_low_coverage_does_not_replace_good_cache(tmp_path):
    p = tmp_path / "scan_cache.json"
    good = _payload(run_scan(["A", "B", "C", "D"], "6mo",
                             lambda t, p_: {k: _trend_df() for k in ["A", "B", "C", "D"]}))
    commit_scan(p, good)
    # only 1 of 4 valid -> ratio 0.25 < 0.5
    partial = _payload(run_scan(["A", "B", "C", "D"], "6mo",
                                lambda t, p_: {"A": _trend_df()}))
    res = commit_scan(p, partial, min_coverage=0.5)
    assert res["committed"] is False and res["reason"] == "low_coverage"
    assert load_cache(p)["coverage"]["valid"] == 4


def test_valid_scan_replaces_atomically(tmp_path):
    p = tmp_path / "scan_cache.json"
    good = _payload(run_scan(["A", "B"], "6mo",
                             lambda t, p_: {"A": _trend_df(), "B": _trend_df()}))
    assert commit_scan(p, good)["committed"] is True
    assert not (tmp_path / "scan_cache.json.tmp").exists()  # temp cleaned up
    cache = load_cache(p)
    assert cache["schema_version"] == 2
    assert cache["status"] == "complete"
    assert cache["latest_bar_date"]


def test_status_partial_when_some_missing(tmp_path):
    res = run_scan(["A", "SHORT"], "6mo",
                   lambda t, p_: {"A": _trend_df(), "SHORT": _trend_df(10)})
    payload = _payload(res)
    assert payload["status"] == "partial"


def test_hashes_are_stable_and_order_independent():
    assert universe_hash(["A", "B"]) == universe_hash(["B", "A"])
    assert settings_hash({"a": 1, "b": 2}) == settings_hash({"b": 2, "a": 1})


def test_load_cache_missing_returns_none(tmp_path):
    assert load_cache(tmp_path / "nope.json") is None


def test_load_cache_corrupt_returns_none(tmp_path):
    p = tmp_path / "scan_cache.json"
    p.write_text("{not json")
    assert load_cache(p) is None
