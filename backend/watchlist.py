"""Grouped watchlist persistence with one-way migration from the flat list."""

import json
from pathlib import Path

DEFAULT_GROUP_NAME = "Watchlist"
DEFAULT_TICKERS = ["AAPL", "MSFT"]


def _default():
    return {"groups": [{"name": DEFAULT_GROUP_NAME, "collapsed": False,
                        "tickers": list(DEFAULT_TICKERS)}]}


def _wrap_flat(tickers):
    return {"groups": [{"name": DEFAULT_GROUP_NAME, "collapsed": False,
                        "tickers": list(tickers)}]}


def load_watchlist(path):
    path = Path(path)
    if not path.exists():
        return _default()
    try:
        raw = json.loads(path.read_text())
    except Exception:
        return _default()
    if isinstance(raw, list):               # legacy flat list → migrate
        return _wrap_flat(raw)
    if isinstance(raw, dict) and "groups" in raw:
        return raw
    return _default()


def save_watchlist(path, data):
    Path(path).write_text(json.dumps(data, indent=2))
