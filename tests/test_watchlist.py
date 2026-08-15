import json

from backend.watchlist import load_watchlist, save_watchlist, DEFAULT_GROUP_NAME


def test_missing_file_returns_default(tmp_path):
    data = load_watchlist(tmp_path / "watchlist.json")
    assert data["groups"][0]["name"] == DEFAULT_GROUP_NAME
    assert data["groups"][0]["tickers"] == ["AAPL", "MSFT"]


def test_migrates_flat_list(tmp_path):
    p = tmp_path / "watchlist.json"
    p.write_text(json.dumps(["TSLA", "NVDA"]))
    data = load_watchlist(p)
    assert data["groups"][0]["name"] == DEFAULT_GROUP_NAME
    assert data["groups"][0]["tickers"] == ["TSLA", "NVDA"]
    assert data["groups"][0]["collapsed"] is False


def test_grouped_file_passthrough(tmp_path):
    p = tmp_path / "watchlist.json"
    payload = {"groups": [{"name": "Tech", "collapsed": True, "tickers": ["AAPL"]}]}
    p.write_text(json.dumps(payload))
    data = load_watchlist(p)
    assert data["groups"][0]["name"] == "Tech"
    assert data["groups"][0]["collapsed"] is True


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "watchlist.json"
    payload = {"groups": [{"name": "A", "collapsed": False, "tickers": ["X"]}]}
    save_watchlist(p, payload)
    assert load_watchlist(p) == payload


def test_corrupt_file_returns_default(tmp_path):
    p = tmp_path / "watchlist.json"
    p.write_text("{not valid json")
    data = load_watchlist(p)
    assert data["groups"][0]["name"] == DEFAULT_GROUP_NAME
