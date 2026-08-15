"""yfinance fetching wrappers. `downloader` is injectable for testing."""

import pandas as pd
import yfinance as yf


def _default_download(tickers, **kwargs):
    return yf.download(tickers, progress=False, **kwargs)


def fetch_history(ticker, period, downloader=_default_download):
    df = downloader(ticker, period=period, interval="1d")
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    return df if not df.empty else None


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def fetch_batch(tickers, period, chunk_size=50, downloader=_default_download):
    """Return {ticker: OHLC DataFrame}, skipping symbols with no/thin data."""
    result = {}
    for chunk in _chunks(list(tickers), chunk_size):
        raw = downloader(" ".join(chunk), period=period, interval="1d",
                         group_by="column")
        if raw is None or raw.empty:
            continue
        for sym in chunk:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    sub = raw.xs(sym, axis=1, level=1)
                else:
                    sub = raw  # single-symbol chunk
            except KeyError:
                continue
            sub = sub.dropna()
            if not sub.empty:
                result[sym] = sub
    return result
