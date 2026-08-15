import pandas as pd

from backend.data import fetch_history, fetch_batch


def _single_df():
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    return pd.DataFrame({"Open": [1, 2, 3], "High": [1, 2, 3], "Low": [1, 2, 3],
                         "Close": [1, 2, 3], "Volume": [1, 1, 1]}, index=idx)


def test_fetch_history_flattens_multiindex():
    idx = pd.date_range("2026-01-01", periods=3, freq="B")
    cols = pd.MultiIndex.from_product([["Close", "High", "Low", "Open", "Volume"], ["AAPL"]])
    df = pd.DataFrame(1.0, index=idx, columns=cols)
    out = fetch_history("AAPL", "6mo", downloader=lambda *a, **k: df)
    assert list(out.columns) == ["Close", "High", "Low", "Open", "Volume"]
    assert len(out) == 3


def test_fetch_history_empty_returns_none():
    out = fetch_history("ZZZZ", "6mo", downloader=lambda *a, **k: pd.DataFrame())
    assert out is None


def test_fetch_batch_splits_and_maps():
    calls = []

    def fake_download(tickers, **kwargs):
        calls.append(tickers)
        # yfinance returns MultiIndex (field, ticker) for multi-symbol calls
        syms = tickers.split() if isinstance(tickers, str) else list(tickers)
        idx = pd.date_range("2026-01-01", periods=3, freq="B")
        cols = pd.MultiIndex.from_product(
            [["Open", "High", "Low", "Close", "Volume"], syms])
        return pd.DataFrame(1.0, index=idx, columns=cols)

    result = fetch_batch(["A", "B", "C"], "6mo", chunk_size=2, downloader=fake_download)
    assert set(result.keys()) == {"A", "B", "C"}
    assert all(list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
               for df in result.values())
    assert len(calls) == 2  # 3 tickers, chunk_size 2 → 2 chunks
