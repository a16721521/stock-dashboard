import json

import numpy as np
import pandas as pd

from backend.scan import run_scan, save_cache, load_cache


def _trend_df(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    down = max(1, int(n * 2 / 3))
    close = np.concatenate([np.linspace(100, 60, down), np.linspace(60, 75, n - down)])
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                         "Close": close, "Volume": np.full(n, 1)}, index=idx)


def test_run_scan_produces_rows_with_readings():
    fetched = {"AAA": _trend_df(), "BBB": _trend_df()}
    rows = run_scan(["AAA", "BBB"], "6mo",
                    batch_fetcher=lambda t, p: fetched)
    by = {r["ticker"]: r for r in rows}
    assert set(by) == {"AAA", "BBB"}
    for r in rows:
        assert set(r) >= {"ticker", "price", "wr", "rsi", "stochK"}
        assert -100 <= r["wr"] <= 0
        assert 0 <= r["rsi"] <= 100


def test_run_scan_skips_short_series():
    fetched = {"AAA": _trend_df(), "SHORT": _trend_df(10)}
    rows = run_scan(["AAA", "SHORT"], "6mo",
                    batch_fetcher=lambda t, p: fetched)
    assert {r["ticker"] for r in rows} == {"AAA"}


def test_cache_roundtrip(tmp_path):
    p = tmp_path / "scan_cache.json"
    rows = [{"ticker": "AAA", "price": 1.0, "wr": -50, "rsi": 50, "stochK": 50}]
    save_cache(p, rows, "sp500+nasdaq100", scanned_at="2026-08-14T20:00:00-04:00")
    cache = load_cache(p)
    assert cache["rows"] == rows
    assert cache["scanned_at"] == "2026-08-14T20:00:00-04:00"
    assert cache["universe"] == "sp500+nasdaq100"


def test_load_cache_missing_returns_none(tmp_path):
    assert load_cache(tmp_path / "nope.json") is None
