"""Marketwide scan: raw indicator readings per ticker + on-disk cache."""

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.indicators import build_indicator_frame

MIN_ROWS = 20


def run_scan(tickers, period, batch_fetcher):
    """Return raw readings [{ticker, price, wr, rsi, stochK}, ...].

    batch_fetcher(tickers, period) -> {ticker: OHLC DataFrame}.
    """
    frames = batch_fetcher(tickers, period)
    rows = []
    for ticker, df in frames.items():
        if df is None or len(df) < MIN_ROWS:
            continue
        ind = build_indicator_frame(df)
        last = ind.iloc[-1]
        if last[["WilliamsR", "RSI", "StochK"]].isna().any():
            continue
        rows.append({
            "ticker": ticker,
            "price": round(float(last["Close"]), 2),
            "wr": round(float(last["WilliamsR"]), 1),
            "rsi": round(float(last["RSI"]), 1),
            "stochK": round(float(last["StochK"]), 1),
        })
    return rows


def save_cache(path, rows, universe, scanned_at=None):
    if scanned_at is None:
        scanned_at = datetime.now(timezone.utc).isoformat()
    payload = {"scanned_at": scanned_at, "universe": universe, "rows": rows}
    Path(path).write_text(json.dumps(payload, indent=2))
    return payload


def load_cache(path):
    path = Path(path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None
