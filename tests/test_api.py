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


def _client(tmp_path):
    app = create_app(
        data_dir=tmp_path,
        ticker_fetcher=lambda ticker, period: _trend_df(),
        batch_fetcher=lambda tickers, period: {t: _trend_df() for t in tickers},
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
    assert body["settings_hash"]
