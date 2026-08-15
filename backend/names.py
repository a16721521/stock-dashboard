"""Company-name resolution with a small on-disk cache.

Names come from yfinance's `.info` (one network call per unseen ticker), then
are cached to disk so repeat views are instant. `fetcher` is injectable so
tests never hit the network. A failed/empty lookup returns None and is not
cached, so it can be retried on a later view."""

import json
from pathlib import Path

import yfinance as yf


def _default_fetcher(ticker):
    info = yf.Ticker(ticker).info
    return info.get("longName") or info.get("shortName")


def load_cache(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_name(ticker, path, fetcher=_default_fetcher):
    ticker = ticker.upper()
    cache = load_cache(path)
    if ticker in cache:
        return cache[ticker]
    try:
        name = fetcher(ticker)
    except Exception:
        name = None
    if name:
        cache[ticker] = name
        Path(path).write_text(json.dumps(cache, indent=2))
    return name
