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
    assert {"dates", "close", "wr", "rsi", "stochK", "stochD"} <= set(body["series"])
    assert "signal" in body["latest"] and "score" in body["latest"]


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


def test_scan_run_and_get(tmp_path):
    c = _client(tmp_path)
    assert c.post("/api/scan/run").status_code in (200, 202)
    body = c.get("/api/scan?tab=top_buy").json()
    assert "rows" in body and "scanned_at" in body
    assert body["rows"], "scan should produce ranked rows"
    assert body["rows"][0]["signal"]  # enriched with signal
