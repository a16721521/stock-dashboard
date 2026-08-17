import json

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.app import create_app


def _trend_df(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    down = max(1, int(n * 2 / 3))
    close = np.concatenate([np.linspace(100, 60, down), np.linspace(60, 75, n - down)])
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                         "Close": close, "Volume": np.full(n, 1)}, index=idx)


def _client(tmp_path, batch_fetcher=None):
    app = create_app(
        data_dir=tmp_path,
        ticker_fetcher=lambda ticker, period: _trend_df(),
        batch_fetcher=batch_fetcher or (lambda tickers, period: {t: _trend_df() for t in tickers}),
        name_fetcher=lambda ticker: f"{ticker} Inc.",
    )
    return TestClient(app)


def test_get_watchlist_default(tmp_path):
    c = _client(tmp_path)
    r = c.get("/api/watchlist")
    assert r.status_code == 200
    assert r.json()["groups"][0]["tickers"] == ["AAPL", "MSFT"]


def test_put_watchlist_persists(tmp_path):
    c = _client(tmp_path)
    payload = {"groups": [{"name": "Tech", "collapsed": False, "tickers": ["NVDA"]}]}
    assert c.put("/api/watchlist", json=payload).status_code == 200
    assert c.get("/api/watchlist").json() == payload


def test_get_ticker_returns_series_and_signal(tmp_path):
    c = _client(tmp_path)
    r = c.get("/api/ticker/AAPL")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["name"] == "AAPL Inc."
    assert {"dates", "close", "wr", "rsi", "stochK", "stochD"} <= set(body["series"])
    assert "state" in body["latest"] and "research_status" in body["latest"]
    assert body["latest"]["research_status"] == "Observation"
    assert body["bar_status"] in ("final", "provisional", "stale", "unknown")


def test_get_ticker_unknown_returns_404(tmp_path):
    app = create_app(data_dir=tmp_path,
                     ticker_fetcher=lambda ticker, period: None,
                     batch_fetcher=lambda tickers, period: {})
    c = TestClient(app)
    assert c.get("/api/ticker/ZZZZ").status_code == 404


def test_settings_get_and_put(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/settings").json()["lookback"] == "6mo"
    new = c.get("/api/settings").json()
    new["thresholds"]["rsi_oversold"] = 25
    assert c.put("/api/settings", json=new).status_code == 200
    assert c.get("/api/settings").json()["thresholds"]["rsi_oversold"] == 25


def test_put_invalid_settings_is_rejected_and_not_persisted(tmp_path):
    c = _client(tmp_path)
    good = c.get("/api/settings").json()
    bad = c.get("/api/settings").json()
    bad["thresholds"]["rsi_oversold"] = 0  # boundary -> would /0 in ranking
    r = c.put("/api/settings", json=bad)
    assert r.status_code == 422
    # unchanged on disk
    assert c.get("/api/settings").json() == good


def test_scan_run_and_get(tmp_path):
    c = _client(tmp_path)
    assert c.post("/api/scan/run").status_code in (200, 202)
    body = c.get("/api/scan?tab=most_oversold").json()
    assert "rows" in body and "scanned_at" in body
    assert body["rows"], "scan should produce ranked rows"
    assert body["rows"][0]["state"]  # enriched with factual state
    assert body["rows"][0]["research_status"] == "Observation"
    assert body["status"] in ("complete", "partial")
    assert body["coverage"]["valid"] > 0
    assert body["date_coverage"] is not None
    assert body["configuration_compatible"] is True


def test_concurrent_scan_is_rejected_with_409(tmp_path):
    c = _client(tmp_path)
    # Simulate a scan already in progress by holding the lock.
    assert c.app.state.scan_lock.acquire(blocking=False)
    try:
        assert c.post("/api/scan/run").status_code == 409
    finally:
        c.app.state.scan_lock.release()
    # Once released, a scan runs normally again.
    assert c.post("/api/scan/run").status_code == 200


def test_data_status_reports_freshness_and_hashes(tmp_path):
    c = _client(tmp_path)
    c.post("/api/scan/run")
    body = c.get("/api/data-status").json()
    assert "expected_session_date" in body
    assert "bar_status" in body
    assert body["cache_status"] in ("complete", "partial")
    assert body["algorithm_version"] == "indicators-v2"
    assert isinstance(body["warnings"], list)
    assert body["calculation_hash"]
    assert body["settings_hash"]
    assert body["configuration_compatible"] is True
    assert body["settings_valid"] is True
    assert body["last_success"]["completed_at"]
    assert body["last_attempt"]["commit_outcome"]["committed"] is True


# ---------------------------------------------------------------------------
# P1-4: a lookback change makes the existing cache incompatible until a
# rescan happens — it must not be silently treated as still valid.
# ---------------------------------------------------------------------------

def test_changing_lookback_marks_cache_incompatible(tmp_path):
    c = _client(tmp_path)
    c.post("/api/scan/run")
    assert c.get("/api/scan").json()["configuration_compatible"] is True

    settings = c.get("/api/settings").json()
    settings["lookback"] = "1y"
    assert c.put("/api/settings", json=settings).status_code == 200

    # No rescan happened yet -> the cached rows were computed under the OLD
    # lookback and must now be flagged incompatible, not silently reused.
    scan_body = c.get("/api/scan").json()
    assert scan_body["configuration_compatible"] is False

    status_body = c.get("/api/data-status").json()
    assert status_body["configuration_compatible"] is False
    assert any("configuration" in w.lower() for w in status_body["warnings"])


def test_threshold_change_alone_stays_compatible(tmp_path):
    # Thresholds only re-rank already-cached raw readings; they don't require
    # a rescan (ranking_hash is informational, not a needs_scan gate).
    c = _client(tmp_path)
    c.post("/api/scan/run")
    settings = c.get("/api/settings").json()
    settings["thresholds"]["rsi_oversold"] = 25
    c.put("/api/settings", json=settings)
    assert c.get("/api/scan").json()["configuration_compatible"] is True


# ---------------------------------------------------------------------------
# P1-3: a failed refresh must remain visible even though the good cache is
# preserved untouched.
# ---------------------------------------------------------------------------

def test_failed_refresh_is_visible_while_good_cache_preserved(tmp_path):
    calls = {"n": 0}

    def flaky_fetcher(tickers, period):
        calls["n"] += 1
        if calls["n"] == 1:
            return {t: _trend_df() for t in tickers}   # first scan succeeds
        return {}                                       # second scan fails

    c = _client(tmp_path, batch_fetcher=flaky_fetcher)
    first = c.post("/api/scan/run").json()
    assert first["committed"] is True

    second = c.post("/api/scan/run").json()
    assert second["committed"] is False

    # The good cache is still what /api/scan serves.
    scan_body = c.get("/api/scan").json()
    assert scan_body["rows"], "the earlier good scan must still be served"

    status = c.get("/api/data-status").json()
    assert status["last_success"]["completed_at"]
    assert status["last_attempt"]["commit_outcome"]["committed"] is False
    assert any("failed" in w.lower() for w in status["warnings"])


# ---------------------------------------------------------------------------
# P2-1: an invalid settings.json on disk must be flagged, not silently used.
# ---------------------------------------------------------------------------

def test_data_status_warns_on_older_bars_not_on_provisional_newer(tmp_path):
    # Caught during live verification: a scan run intraday correctly returns
    # PROVISIONAL bars newer than the last closed session (expected). Those
    # must not be reported as "stale" or "uneven freshness" — that warning
    # should be reserved for the real P1-2 concern (some symbols genuinely
    # older than others), which bar_status alone doesn't catch.
    c = _client(tmp_path)
    cache_path = tmp_path / "scan_cache.json"
    base = {
        "schema_version": 2, "algorithm_version": "indicators-v2",
        "calculation_hash": "x", "ranking_hash": "y",
        "universe_id": "u", "universe_hash": "z", "lookback": "6mo",
        "started_at": "2026-08-17T10:00:00+00:00", "completed_at": "2026-08-17T10:00:00+00:00",
        "expected_session_date": "2026-08-14", "latest_bar_date": "2026-08-17",
        "status": "complete",
        "coverage": {"requested": 2, "downloaded": 2, "valid": 2, "missing": 0,
                    "ratio": 1.0, "missing_symbols": []},
        "errors": [], "scanned_at": "2026-08-17T10:00:00+00:00",
    }

    # All rows newer than expected (intraday/provisional) -> no "uneven" warning.
    newer = {**base, "date_coverage": {"expected_date": "2026-08-14", "expected_date_count": 0,
                                       "older_date_count": 0, "newer_date_count": 2,
                                       "expected_date_ratio": 0.0}}
    cache_path.write_text(json.dumps(newer))
    warnings = c.get("/api/data-status").json()["warnings"]
    assert not any("uneven" in w.lower() for w in warnings)

    # One row genuinely older than the other -> the real masking concern fires.
    mixed = {**base, "date_coverage": {"expected_date": "2026-08-14", "expected_date_count": 1,
                                       "older_date_count": 1, "newer_date_count": 0,
                                       "expected_date_ratio": 0.5}}
    cache_path.write_text(json.dumps(mixed))
    warnings2 = c.get("/api/data-status").json()["warnings"]
    assert any("uneven" in w.lower() for w in warnings2)


def test_data_status_flags_invalid_settings_file(tmp_path):
    c = _client(tmp_path)
    (tmp_path / "settings.json").write_text(json.dumps({
        "thresholds": {"wr_oversold": -100, "wr_overbought": -20,
                       "rsi_oversold": 30, "rsi_overbought": 70,
                       "stoch_oversold": 20, "stoch_overbought": 80},
        "lookback": "6mo",
    }))
    body = c.get("/api/data-status").json()
    assert body["settings_valid"] is False
    assert any("invalid" in w.lower() for w in body["warnings"])
    # get_settings itself must still return a safe, valid config
    assert c.get("/api/settings").json()["thresholds"]["wr_oversold"] == -80
