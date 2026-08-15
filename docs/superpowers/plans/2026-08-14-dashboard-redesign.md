# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Streamlit dashboard with a custom local web app — FastAPI JSON backend reusing the existing indicator math, plus a no-build HTML/CSS/JS frontend with a grouped drag-orderable watchlist, a detail panel, and a tab-ranked marketwide grid over the S&P 500 + Nasdaq-100.

**Architecture:** A `backend/` Python package owns data fetching (yfinance), indicator/signal math, ranking, grouped-watchlist persistence, settings, the marketwide scan + on-disk cache, and a staleness-driven scheduler. A FastAPI app exposes JSON endpoints and serves a static `frontend/` (vanilla JS split by panel, SortableJS for drag/drop, Plotly.js for charts). The legacy `app.py` (Streamlit) is kept until the new app works end-to-end, then removed.

**Tech Stack:** Python 3.14, FastAPI, uvicorn, yfinance, pandas, numpy, pytest; vanilla JS, SortableJS, Plotly.js.

---

## Conventions

- All Python commands run through the existing venv: `./.venv/bin/python`, `./.venv/bin/pytest`, `./.venv/bin/uvicorn`.
- Run tests from the project root. Tests never hit the network — yfinance is always mocked.
- Commit after each task with the message shown in its final step.
- Working directory for all commands: `/Users/frpo/Desktop/Indicator Dashboard`.

## Target File Structure

```
backend/
  __init__.py
  indicators.py     # williams_r, rsi, stochastic, build_indicator_frame, classify_signal, DEFAULT_THRESHOLDS
  ranking.py        # oversold/overbought magnitude, rank_rows
  data.py           # fetch_history (single), fetch_batch (chunked)
  watchlist.py      # load/save/migrate grouped watchlist
  settings.py       # load/save settings (thresholds + lookback)
  universe.py       # load S&P500 + Nasdaq100 tickers from data files
  scan.py           # run_scan, cache load/save
  scheduler.py      # most_recent_close, is_stale, background timer
  app.py            # FastAPI: JSON routes + static frontend
  constituents/
    sp500.txt
    nasdaq100.txt
frontend/
  index.html
  css/style.css
  js/api.js         # fetch helpers
  js/state.js       # shared client state
  js/watchlist.js   # left panel + drag/drop
  js/detail.js      # right panel + Plotly
  js/marketwide.js  # bottom grid + tabs
  js/settings.js    # settings modal
  js/main.js        # bootstrap + wiring
  vendor/sortable.min.js
  vendor/plotly.min.js
tests/
  __init__.py
  conftest.py
  test_indicators.py
  test_ranking.py
  test_watchlist.py
  test_settings.py
  test_scan.py
  test_scheduler.py
  test_api.py
run.sh
```

---

## PHASE 0 — Project scaffolding & dependencies

### Task 0: Dev environment, packages, pytest

**Files:**
- Modify: `requirements.txt`
- Create: `backend/__init__.py`, `tests/__init__.py`, `tests/conftest.py`, `pytest.ini`

- [ ] **Step 1: Update requirements.txt**

Replace the whole file with:

```
fastapi>=0.110
uvicorn>=0.29
yfinance>=0.2.40
pandas>=2.1
numpy>=1.24
pytest>=8.0
httpx>=0.27
```

(`httpx` is needed by FastAPI's `TestClient`. `streamlit` and `plotly` are removed — the browser uses Plotly.js.)

- [ ] **Step 2: Install into the existing venv**

Run: `./.venv/bin/pip install -r requirements.txt`
Expected: installs fastapi, uvicorn, pytest, httpx; ends with "Successfully installed ...".

- [ ] **Step 3: Create package/test init files**

Create `backend/__init__.py`:
```python
```
(empty file)

Create `tests/__init__.py`:
```python
```
(empty file)

- [ ] **Step 4: Create pytest.ini**

Create `pytest.ini`:
```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -q
```

- [ ] **Step 5: Create conftest.py with a synthetic OHLC fixture**

Create `tests/conftest.py`:
```python
import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def ohlc():
    """Deterministic 60-day OHLC frame with a clear downtrend then bounce,
    enough rows for 14-period indicators to be non-NaN at the tail."""
    n = 60
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    # Falling then rising close, with High/Low bracketing it.
    close = np.concatenate([np.linspace(100, 60, 40), np.linspace(60, 75, 20)])
    high = close + 1.5
    low = close - 1.5
    open_ = close + 0.2
    vol = np.full(n, 1_000_000)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )
```

- [ ] **Step 6: Verify pytest collects nothing yet (no tests) cleanly**

Run: `./.venv/bin/pytest`
Expected: "no tests ran" (exit code 5 is fine) — confirms pytest + config load without import errors.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini backend/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: add FastAPI/pytest deps and test scaffold"
```

---

## PHASE 1 — Backend core: indicators, ranking, persistence

### Task 1: Extract indicators into `backend/indicators.py`

**Files:**
- Create: `backend/indicators.py`
- Test: `tests/test_indicators.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_indicators.py`:
```python
import numpy as np
import pandas as pd

from backend.indicators import (
    williams_r, rsi, stochastic, build_indicator_frame,
    classify_signal, DEFAULT_THRESHOLDS,
)


def test_williams_r_range_and_tail(ohlc):
    wr = williams_r(ohlc)
    tail = wr.dropna()
    assert not tail.empty
    assert (tail <= 0).all() and (tail >= -100).all()


def test_rsi_range(ohlc):
    r = rsi(ohlc).dropna()
    assert not r.empty
    assert (r >= 0).all() and (r <= 100).all()


def test_stochastic_range(ohlc):
    k, d = stochastic(ohlc)
    kk = k.dropna()
    assert not kk.empty
    assert (kk >= 0).all() and (kk <= 100).all()


def test_build_indicator_frame_columns(ohlc):
    out = build_indicator_frame(ohlc)
    for col in ["WilliamsR", "RSI", "StochK", "StochD"]:
        assert col in out.columns


def test_classify_all_oversold_is_strong_buy():
    t = DEFAULT_THRESHOLDS
    label, score = classify_signal(-90, 20, 10, t)
    assert label == "Strong Buy" and score == 3


def test_classify_all_overbought_is_strong_sell():
    t = DEFAULT_THRESHOLDS
    label, score = classify_signal(-10, 80, 90, t)
    assert label == "Strong Sell" and score == -3


def test_classify_neutral():
    t = DEFAULT_THRESHOLDS
    label, score = classify_signal(-50, 50, 50, t)
    assert label == "Neutral" and score == 0
```

- [ ] **Step 2: Run tests, expect failure**

Run: `./.venv/bin/pytest tests/test_indicators.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.indicators'`.

- [ ] **Step 3: Implement `backend/indicators.py`**

Create `backend/indicators.py` (functions ported verbatim from the current `app.py`, plus thresholds):
```python
"""Indicator math and signal classification — plain pandas, no TA library."""

import numpy as np
import pandas as pd

DEFAULT_THRESHOLDS = {
    "wr_oversold": -80, "wr_overbought": -20,
    "rsi_oversold": 30, "rsi_overbought": 70,
    "stoch_oversold": 20, "stoch_overbought": 80,
}


def williams_r(df, period=14):
    highest_high = df["High"].rolling(period).max()
    lowest_low = df["Low"].rolling(period).min()
    wr = (highest_high - df["Close"]) / (highest_high - lowest_low) * -100
    return wr.replace([np.inf, -np.inf], np.nan)


def rsi(df, period=14):
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    out = 100 - (100 / (1 + rs))
    return out.replace([np.inf, -np.inf], 100)


def stochastic(df, k_period=14, d_period=3, smooth_k=3):
    lowest_low = df["Low"].rolling(k_period).min()
    highest_high = df["High"].rolling(k_period).max()
    raw_k = (df["Close"] - lowest_low) / (highest_high - lowest_low) * 100
    k = raw_k.rolling(smooth_k).mean().replace([np.inf, -np.inf], np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def build_indicator_frame(df):
    out = df.copy()
    out["WilliamsR"] = williams_r(out)
    out["RSI"] = rsi(out)
    out["StochK"], out["StochD"] = stochastic(out)
    return out


def classify_signal(wr, rsi_val, stoch_k, t):
    oversold = 0
    overbought = 0
    if wr <= t["wr_oversold"]:
        oversold += 1
    elif wr >= t["wr_overbought"]:
        overbought += 1
    if rsi_val <= t["rsi_oversold"]:
        oversold += 1
    elif rsi_val >= t["rsi_overbought"]:
        overbought += 1
    if stoch_k <= t["stoch_oversold"]:
        oversold += 1
    elif stoch_k >= t["stoch_overbought"]:
        overbought += 1

    if oversold >= 3:
        return "Strong Buy", 3
    if oversold == 2:
        return "Buy", 2
    if oversold == 1:
        return "Watch (oversold)", 1
    if overbought >= 3:
        return "Strong Sell", -3
    if overbought == 2:
        return "Sell", -2
    if overbought == 1:
        return "Watch (overbought)", -1
    return "Neutral", 0
```

- [ ] **Step 4: Run tests, expect pass**

Run: `./.venv/bin/pytest tests/test_indicators.py`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/indicators.py tests/test_indicators.py
git commit -m "feat: extract indicator math into backend.indicators"
```

---

### Task 2: Ranking magnitudes + `rank_rows` in `backend/ranking.py`

**Files:**
- Create: `backend/ranking.py`
- Test: `tests/test_ranking.py`

**Design:** ranking is computed at request time from raw readings so threshold changes re-rank without rescanning. `oversold_magnitude`/`overbought_magnitude` return 0..3 (sum of three normalized, clamped distances past threshold). `rank_rows(rows, thresholds, tab)` attaches `signal`, `score`, `magnitude` to each row and returns them sorted.

- [ ] **Step 1: Write failing tests**

Create `tests/test_ranking.py`:
```python
from backend.indicators import DEFAULT_THRESHOLDS
from backend.ranking import oversold_magnitude, overbought_magnitude, rank_rows


def test_oversold_magnitude_deep_is_near_three():
    # wr=-100 (max), rsi=0, stoch=0 → all three fully past oversold thresholds
    m = oversold_magnitude(-100, 0, 0, DEFAULT_THRESHOLDS)
    assert 2.9 <= m <= 3.0


def test_oversold_magnitude_none_is_zero():
    m = oversold_magnitude(-50, 50, 50, DEFAULT_THRESHOLDS)
    assert m == 0.0


def test_overbought_magnitude_extreme_is_near_three():
    m = overbought_magnitude(0, 100, 100, DEFAULT_THRESHOLDS)
    assert 2.9 <= m <= 3.0


def test_rank_rows_top_buy_orders_most_oversold_first():
    rows = [
        {"ticker": "A", "price": 1, "wr": -50, "rsi": 50, "stochK": 50},   # neutral
        {"ticker": "B", "price": 1, "wr": -100, "rsi": 5, "stochK": 5},    # strong buy, deep
        {"ticker": "C", "price": 1, "wr": -85, "rsi": 25, "stochK": 50},   # buy, shallow
    ]
    out = rank_rows(rows, DEFAULT_THRESHOLDS, "top_buy")
    assert [r["ticker"] for r in out] == ["B", "C", "A"]
    assert out[0]["signal"] == "Strong Buy"


def test_rank_rows_top_sell_orders_most_overbought_first():
    rows = [
        {"ticker": "A", "price": 1, "wr": -50, "rsi": 50, "stochK": 50},
        {"ticker": "B", "price": 1, "wr": 0, "rsi": 95, "stochK": 95},
        {"ticker": "C", "price": 1, "wr": -15, "rsi": 75, "stochK": 50},
    ]
    out = rank_rows(rows, DEFAULT_THRESHOLDS, "top_sell")
    assert [r["ticker"] for r in out] == ["B", "C", "A"]
    assert out[0]["signal"] == "Strong Sell"
```

- [ ] **Step 2: Run tests, expect failure**

Run: `./.venv/bin/pytest tests/test_ranking.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.ranking'`.

- [ ] **Step 3: Implement `backend/ranking.py`**

Create `backend/ranking.py`:
```python
"""Marketwide ranking: how far past threshold each name is, and tab ordering."""

from backend.indicators import classify_signal


def _clamp01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def oversold_magnitude(wr, rsi_val, stoch_k, t):
    """Sum of normalized distances *below* each oversold threshold, in [0, 3]."""
    wr_term = _clamp01((t["wr_oversold"] - wr) / (t["wr_oversold"] - (-100)))
    rsi_term = _clamp01((t["rsi_oversold"] - rsi_val) / t["rsi_oversold"])
    stoch_term = _clamp01((t["stoch_oversold"] - stoch_k) / t["stoch_oversold"])
    return wr_term + rsi_term + stoch_term


def overbought_magnitude(wr, rsi_val, stoch_k, t):
    """Sum of normalized distances *above* each overbought threshold, in [0, 3]."""
    wr_term = _clamp01((wr - t["wr_overbought"]) / (0 - t["wr_overbought"]))
    rsi_term = _clamp01((rsi_val - t["rsi_overbought"]) / (100 - t["rsi_overbought"]))
    stoch_term = _clamp01((stoch_k - t["stoch_overbought"]) / (100 - t["stoch_overbought"]))
    return wr_term + rsi_term + stoch_term


def rank_rows(rows, thresholds, tab):
    """Return rows enriched with signal/score/magnitude, sorted for the tab.

    tab: "top_buy" (most oversold first) or "top_sell" (most overbought first).
    """
    enriched = []
    for r in rows:
        signal, score = classify_signal(r["wr"], r["rsi"], r["stochK"], thresholds)
        if tab == "top_sell":
            magnitude = overbought_magnitude(r["wr"], r["rsi"], r["stochK"], thresholds)
            sort_key = (-score, magnitude)
        else:  # top_buy default
            magnitude = oversold_magnitude(r["wr"], r["rsi"], r["stochK"], thresholds)
            sort_key = (score, magnitude)
        enriched.append({**r, "signal": signal, "score": score,
                         "magnitude": round(magnitude, 3), "_sort": sort_key})
    enriched.sort(key=lambda r: r["_sort"], reverse=True)
    for r in enriched:
        del r["_sort"]
    return enriched
```

- [ ] **Step 4: Run tests, expect pass**

Run: `./.venv/bin/pytest tests/test_ranking.py`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/ranking.py tests/test_ranking.py
git commit -m "feat: add marketwide ranking magnitudes and rank_rows"
```

---

### Task 3: Grouped watchlist persistence + migration in `backend/watchlist.py`

**Files:**
- Create: `backend/watchlist.py`
- Test: `tests/test_watchlist.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_watchlist.py`:
```python
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
```

- [ ] **Step 2: Run tests, expect failure**

Run: `./.venv/bin/pytest tests/test_watchlist.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.watchlist'`.

- [ ] **Step 3: Implement `backend/watchlist.py`**

Create `backend/watchlist.py`:
```python
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
```

- [ ] **Step 4: Run tests, expect pass**

Run: `./.venv/bin/pytest tests/test_watchlist.py`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/watchlist.py tests/test_watchlist.py
git commit -m "feat: grouped watchlist persistence with flat-list migration"
```

---

### Task 4: Settings persistence in `backend/settings.py`

**Files:**
- Create: `backend/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_settings.py`:
```python
import json

from backend.settings import load_settings, save_settings, DEFAULT_SETTINGS


def test_missing_file_returns_defaults(tmp_path):
    s = load_settings(tmp_path / "settings.json")
    assert s == DEFAULT_SETTINGS
    assert s["thresholds"]["rsi_oversold"] == 30
    assert s["lookback"] == "6mo"


def test_partial_file_is_merged_over_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"lookback": "1y"}))
    s = load_settings(p)
    assert s["lookback"] == "1y"
    assert s["thresholds"]["rsi_oversold"] == 30  # default preserved


def test_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    s = load_settings(p)
    s["lookback"] = "2y"
    save_settings(p, s)
    assert load_settings(p)["lookback"] == "2y"
```

- [ ] **Step 2: Run tests, expect failure**

Run: `./.venv/bin/pytest tests/test_settings.py`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `backend/settings.py`**

Create `backend/settings.py`:
```python
"""Persisted settings: signal thresholds + lookback window."""

import json
from pathlib import Path

from backend.indicators import DEFAULT_THRESHOLDS

DEFAULT_SETTINGS = {
    "thresholds": dict(DEFAULT_THRESHOLDS),
    "lookback": "6mo",
}
LOOKBACK_CHOICES = ["3mo", "6mo", "1y", "2y"]


def load_settings(path):
    path = Path(path)
    merged = {"thresholds": dict(DEFAULT_THRESHOLDS),
              "lookback": DEFAULT_SETTINGS["lookback"]}
    if path.exists():
        try:
            raw = json.loads(path.read_text())
        except Exception:
            raw = {}
        if isinstance(raw, dict):
            if isinstance(raw.get("thresholds"), dict):
                merged["thresholds"].update(raw["thresholds"])
            if raw.get("lookback") in LOOKBACK_CHOICES:
                merged["lookback"] = raw["lookback"]
    return merged


def save_settings(path, data):
    Path(path).write_text(json.dumps(data, indent=2))
```

- [ ] **Step 4: Run tests, expect pass**

Run: `./.venv/bin/pytest tests/test_settings.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/settings.py tests/test_settings.py
git commit -m "feat: settings persistence with defaults merge"
```

---

## PHASE 2 — Data, universe, scan, scheduler

### Task 5: yfinance wrappers in `backend/data.py`

**Files:**
- Create: `backend/data.py`
- Test: `tests/test_data.py`

**Design:** `fetch_history(ticker, period)` mirrors the current `fetch_data` (single symbol, flatten MultiIndex, dropna). `fetch_batch(tickers, period, chunk_size=50)` calls `yf.download` per chunk and returns `{ticker: DataFrame}`, skipping empties. Both accept an injectable `downloader` so tests never hit the network.

- [ ] **Step 1: Write failing tests**

Create `tests/test_data.py`:
```python
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
```

- [ ] **Step 2: Run tests, expect failure**

Run: `./.venv/bin/pytest tests/test_data.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.data'`.

- [ ] **Step 3: Implement `backend/data.py`**

Create `backend/data.py`:
```python
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
```

- [ ] **Step 4: Run tests, expect pass**

Run: `./.venv/bin/pytest tests/test_data.py`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/data.py tests/test_data.py
git commit -m "feat: yfinance single + batched fetch wrappers"
```

---

### Task 6: Constituent lists + `backend/universe.py`

**Files:**
- Create: `backend/constituents/sp500.txt`, `backend/constituents/nasdaq100.txt`, `backend/universe.py`
- Test: `tests/test_universe.py`

**Note for implementer:** the two `.txt` files hold one ticker per line. Populate them from a current source (e.g. Wikipedia's S&P 500 and Nasdaq-100 constituent tables) at implementation time. The exact membership is not correctness-critical for the code; the loader is what we test. Use `-`→`.` normalization is NOT applied here (yfinance uses `BRK-B` style already). Seed each file with at least the few tickers below so tests and a first run work; expand to the full lists before shipping.

- [ ] **Step 1: Create seed constituent files**

Create `backend/constituents/sp500.txt`:
```
AAPL
MSFT
NVDA
AMZN
GOOGL
META
BRK-B
JPM
```

Create `backend/constituents/nasdaq100.txt`:
```
AAPL
MSFT
NVDA
AMZN
GOOGL
META
TSLA
AVGO
```
(Implementer: replace both with the full ~503 / ~100 lists before shipping. Overlap is expected and de-duplicated by the loader.)

- [ ] **Step 2: Write failing tests**

Create `tests/test_universe.py`:
```python
from backend.universe import load_universe


def test_universe_is_deduped_and_sorted():
    u = load_universe()
    assert "AAPL" in u
    assert "TSLA" in u          # nasdaq-only seed
    assert "JPM" in u           # sp500-only seed
    assert len(u) == len(set(u))  # no duplicates
    assert u == sorted(u)
```

- [ ] **Step 3: Run test, expect failure**

Run: `./.venv/bin/pytest tests/test_universe.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.universe'`.

- [ ] **Step 4: Implement `backend/universe.py`**

Create `backend/universe.py`:
```python
"""Load the marketwide scan universe (S&P 500 + Nasdaq-100), de-duplicated."""

from pathlib import Path

_DIR = Path(__file__).parent / "constituents"


def _read(name):
    text = (_DIR / name).read_text()
    return [line.strip() for line in text.splitlines() if line.strip()]


def load_universe():
    tickers = set(_read("sp500.txt")) | set(_read("nasdaq100.txt"))
    return sorted(tickers)
```

- [ ] **Step 5: Run test, expect pass**

Run: `./.venv/bin/pytest tests/test_universe.py`
Expected: PASS (1 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/constituents backend/universe.py tests/test_universe.py
git commit -m "feat: universe loader + seed constituent lists"
```

---

### Task 7: Marketwide scan + cache in `backend/scan.py`

**Files:**
- Create: `backend/scan.py`
- Test: `tests/test_scan.py`

**Design:** `run_scan(tickers, period, batch_fetcher)` computes raw readings per ticker (price/wr/rsi/stochK) from the last valid row, skips too-short/NaN tails, returns a list of row dicts. `save_cache`/`load_cache` persist `{scanned_at, universe, rows}`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_scan.py`:
```python
import json

import numpy as np
import pandas as pd

from backend.scan import run_scan, save_cache, load_cache


def _trend_df(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    close = np.concatenate([np.linspace(100, 60, 40), np.linspace(60, 75, 20)])
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
```

- [ ] **Step 2: Run tests, expect failure**

Run: `./.venv/bin/pytest tests/test_scan.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.scan'`.

- [ ] **Step 3: Implement `backend/scan.py`**

Create `backend/scan.py`:
```python
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
```

- [ ] **Step 4: Run tests, expect pass**

Run: `./.venv/bin/pytest tests/test_scan.py`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/scan.py tests/test_scan.py
git commit -m "feat: marketwide scan + cache"
```

---

### Task 8: Staleness logic in `backend/scheduler.py`

**Files:**
- Create: `backend/scheduler.py`
- Test: `tests/test_scheduler.py`

**Design:** pure decision functions are unit-tested; the live timer thread is a thin wrapper started by the app. `most_recent_close(now)` returns the datetime of the last weekday 16:00 US/Eastern at or before `now`. `is_stale(scanned_at, now)` is true when there is no scan or the scan predates that close. Holidays are ignored (a rare unnecessary scan is acceptable) — documented limitation.

- [ ] **Step 1: Write failing tests**

Create `tests/test_scheduler.py`:
```python
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.scheduler import most_recent_close, is_stale

ET = ZoneInfo("America/New_York")


def test_most_recent_close_same_day_after_4pm():
    now = datetime(2026, 8, 14, 17, 0, tzinfo=ET)  # Friday 5pm
    c = most_recent_close(now)
    assert c == datetime(2026, 8, 14, 16, 0, tzinfo=ET)


def test_most_recent_close_before_4pm_uses_prior_weekday():
    now = datetime(2026, 8, 14, 9, 0, tzinfo=ET)  # Friday 9am
    c = most_recent_close(now)
    assert c == datetime(2026, 8, 13, 16, 0, tzinfo=ET)  # Thursday close


def test_most_recent_close_weekend_uses_friday():
    now = datetime(2026, 8, 16, 12, 0, tzinfo=ET)  # Sunday
    c = most_recent_close(now)
    assert c == datetime(2026, 8, 14, 16, 0, tzinfo=ET)  # Friday close


def test_is_stale_true_when_no_scan():
    now = datetime(2026, 8, 14, 17, 0, tzinfo=ET)
    assert is_stale(None, now) is True


def test_is_stale_false_when_scan_after_close():
    now = datetime(2026, 8, 14, 17, 0, tzinfo=ET)
    scanned = datetime(2026, 8, 14, 16, 30, tzinfo=ET).isoformat()
    assert is_stale(scanned, now) is False


def test_is_stale_true_when_scan_before_close():
    now = datetime(2026, 8, 14, 17, 0, tzinfo=ET)
    scanned = datetime(2026, 8, 14, 15, 0, tzinfo=ET).isoformat()  # before today's close
    assert is_stale(scanned, now) is True
```

- [ ] **Step 2: Run tests, expect failure**

Run: `./.venv/bin/pytest tests/test_scheduler.py`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `backend/scheduler.py`**

Create `backend/scheduler.py`:
```python
"""Scan staleness decisions + a lightweight background refresh timer.

Holidays are not modelled; at worst a scan runs on a market holiday, which is
harmless. Daily bars only settle after the US cash close (16:00 ET)."""

import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
CLOSE_HOUR = 16


def most_recent_close(now):
    """Datetime of the last weekday 16:00 ET at or before `now`."""
    now = now.astimezone(ET)
    candidate = now.replace(hour=CLOSE_HOUR, minute=0, second=0, microsecond=0)
    if now < candidate:                 # before today's close → step back a day
        candidate -= timedelta(days=1)
    while candidate.weekday() >= 5:     # Sat=5, Sun=6 → walk back to Friday
        candidate -= timedelta(days=1)
    return candidate


def is_stale(scanned_at, now=None):
    """True if there's no scan or it predates the most recent close."""
    if now is None:
        now = datetime.now(ET)
    if not scanned_at:
        return True
    scanned = datetime.fromisoformat(scanned_at)
    return scanned < most_recent_close(now)


def start_background_timer(run_scan_callback, get_scanned_at, interval_seconds=1800):
    """Every `interval_seconds`, run the scan if stale. Returns the Timer thread.

    run_scan_callback(): performs a scan and writes the cache.
    get_scanned_at(): returns the current cache's scanned_at (or None).
    """
    def _tick():
        try:
            if is_stale(get_scanned_at()):
                run_scan_callback()
        finally:
            timer = threading.Timer(interval_seconds, _tick)
            timer.daemon = True
            timer.start()

    timer = threading.Timer(interval_seconds, _tick)
    timer.daemon = True
    timer.start()
    return timer
```

- [ ] **Step 4: Run tests, expect pass**

Run: `./.venv/bin/pytest tests/test_scheduler.py`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/scheduler.py tests/test_scheduler.py
git commit -m "feat: scan staleness logic + background timer"
```

---

## PHASE 3 — FastAPI application

### Task 9: FastAPI app with data paths, ticker, watchlist, settings

**Files:**
- Create: `backend/app.py`
- Test: `tests/test_api.py`

**Design:** `create_app(data_dir, ticker_fetcher, batch_fetcher)` builds the app with injectable fetchers and a configurable data directory (so tests use `tmp_path` and mocked data). A module-level `app = create_app(...)` with real fetchers is what uvicorn serves. Scan state (`scanning` flag) lives on `app.state`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_api.py`:
```python
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend.app import create_app


def _trend_df(n=60):
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    close = np.concatenate([np.linspace(100, 60, 40), np.linspace(60, 75, 20)])
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
```

- [ ] **Step 2: Run tests, expect failure**

Run: `./.venv/bin/pytest tests/test_api.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app'`.

- [ ] **Step 3: Implement `backend/app.py`**

Create `backend/app.py`:
```python
"""FastAPI app: JSON API + static frontend. Fetchers are injectable for tests."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend import data as data_mod
from backend.indicators import build_indicator_frame, classify_signal
from backend.ranking import rank_rows
from backend.scan import run_scan, save_cache, load_cache
from backend.settings import load_settings, save_settings
from backend.universe import load_universe
from backend.watchlist import load_watchlist, save_watchlist

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def create_app(data_dir, ticker_fetcher=None, batch_fetcher=None):
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    watchlist_path = data_dir / "watchlist.json"
    settings_path = data_dir / "settings.json"
    cache_path = data_dir / "scan_cache.json"

    if ticker_fetcher is None:
        ticker_fetcher = data_mod.fetch_history
    if batch_fetcher is None:
        batch_fetcher = data_mod.fetch_batch

    app = FastAPI(title="Indicator Dashboard")
    app.state.scanning = False

    # ---- Watchlist ----
    @app.get("/api/watchlist")
    def get_watchlist():
        return load_watchlist(watchlist_path)

    @app.put("/api/watchlist")
    def put_watchlist(payload: dict):
        save_watchlist(watchlist_path, payload)
        return {"ok": True}

    # ---- Settings ----
    @app.get("/api/settings")
    def get_settings():
        return load_settings(settings_path)

    @app.put("/api/settings")
    def put_settings(payload: dict):
        save_settings(settings_path, payload)
        return {"ok": True}

    # ---- Ticker detail ----
    @app.get("/api/ticker/{symbol}")
    def get_ticker(symbol: str):
        settings = load_settings(settings_path)
        df = ticker_fetcher(symbol.upper(), settings["lookback"])
        if df is None or len(df) < 20:
            raise HTTPException(status_code=404, detail=f"No data for {symbol}")
        ind = build_indicator_frame(df)
        last = ind.iloc[-1]
        if last[["WilliamsR", "RSI", "StochK"]].isna().any():
            raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")
        signal, score = classify_signal(
            last["WilliamsR"], last["RSI"], last["StochK"], settings["thresholds"])
        return {
            "ticker": symbol.upper(),
            "series": {
                "dates": [d.strftime("%Y-%m-%d") for d in ind.index],
                "close": ind["Close"].round(2).tolist(),
                "wr": ind["WilliamsR"].round(2).where(ind["WilliamsR"].notna(), None).tolist(),
                "rsi": ind["RSI"].round(2).where(ind["RSI"].notna(), None).tolist(),
                "stochK": ind["StochK"].round(2).where(ind["StochK"].notna(), None).tolist(),
                "stochD": ind["StochD"].round(2).where(ind["StochD"].notna(), None).tolist(),
            },
            "latest": {
                "price": round(float(last["Close"]), 2),
                "wr": round(float(last["WilliamsR"]), 1),
                "rsi": round(float(last["RSI"]), 1),
                "stochK": round(float(last["StochK"]), 1),
                "signal": signal,
                "score": score,
            },
            "thresholds": settings["thresholds"],
        }

    # ---- Marketwide scan ----
    def _do_scan():
        settings = load_settings(settings_path)
        universe = load_universe()
        rows = run_scan(universe, settings["lookback"], batch_fetcher)
        save_cache(cache_path, rows, "sp500+nasdaq100")

    @app.post("/api/scan/run")
    def scan_run():
        app.state.scanning = True
        try:
            _do_scan()
        finally:
            app.state.scanning = False
        return {"ok": True}

    @app.get("/api/scan")
    def scan_get(tab: str = "top_buy"):
        cache = load_cache(cache_path)
        settings = load_settings(settings_path)
        if cache is None:
            return {"scanned_at": None, "scanning": app.state.scanning, "rows": []}
        ranked = rank_rows(cache["rows"], settings["thresholds"], tab)
        return {"scanned_at": cache["scanned_at"], "scanning": app.state.scanning,
                "tab": tab, "rows": ranked}

    # ---- Static frontend ----
    if FRONTEND_DIR.exists():
        @app.get("/")
        def index():
            return FileResponse(FRONTEND_DIR / "index.html")
        app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="static")

    return app


# Real app for uvicorn: data files live in the project root.
app = create_app(data_dir=Path(__file__).parent.parent)
```

Note: in this task the module-level `app = create_app(...)` will import fine even though `frontend/` doesn't exist yet (the mount is guarded by `FRONTEND_DIR.exists()`).

- [ ] **Step 4: Run tests, expect pass**

Run: `./.venv/bin/pytest tests/test_api.py`
Expected: PASS (6 passed).

- [ ] **Step 5: Run the whole backend suite**

Run: `./.venv/bin/pytest`
Expected: PASS (all tasks 1–9 green).

- [ ] **Step 6: Commit**

```bash
git add backend/app.py tests/test_api.py
git commit -m "feat: FastAPI app with watchlist, settings, ticker, and scan endpoints"
```

---

### Task 10: Startup scan-if-stale + timer, and `run.sh`

**Files:**
- Modify: `backend/app.py` (add startup hook)
- Create: `run.sh`

- [ ] **Step 1: Add a startup hook to `create_app` (before `return app`)**

In `backend/app.py`, add this just above `return app`:
```python
    @app.on_event("startup")
    def _startup():
        from backend.scheduler import is_stale, start_background_timer
        cache = load_cache(cache_path)
        scanned_at = cache["scanned_at"] if cache else None
        if is_stale(scanned_at):
            import threading
            threading.Thread(target=_wrapped_scan, daemon=True).start()
        start_background_timer(
            run_scan_callback=_wrapped_scan,
            get_scanned_at=lambda: (load_cache(cache_path) or {}).get("scanned_at"),
        )

    def _wrapped_scan():
        app.state.scanning = True
        try:
            _do_scan()
        finally:
            app.state.scanning = False
```

(The initial scan runs on a background thread so the server responds immediately; the frontend polls `/api/scan` and shows progress via the `scanning` flag.)

- [ ] **Step 2: Verify tests still pass (TestClient triggers startup)**

Run: `./.venv/bin/pytest tests/test_api.py -q`
Expected: PASS — the injected `batch_fetcher` makes the startup scan instant and harmless.

- [ ] **Step 3: Create `run.sh`**

Create `run.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec ./.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8000 "$@"
```

- [ ] **Step 4: Make it executable**

Run: `chmod +x run.sh`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py run.sh
git commit -m "feat: startup scan-if-stale, background timer, run.sh launcher"
```

---

## PHASE 4 — Frontend

> Frontend tasks have no unit tests; each ends with an explicit in-browser verification. Start the server once with `./run.sh` and reload after each task. The backend must be running for the API calls to work.

### Task 11: HTML shell + white boxed CSS layout

**Files:**
- Create: `frontend/index.html`, `frontend/css/style.css`
- Create (vendored): `frontend/vendor/sortable.min.js`, `frontend/vendor/plotly.min.js`

- [ ] **Step 1: Vendor the libraries**

Run:
```bash
mkdir -p frontend/vendor frontend/css frontend/js
curl -sL https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js -o frontend/vendor/sortable.min.js
curl -sL https://cdn.plot.ly/plotly-2.32.0.min.js -o frontend/vendor/plotly.min.js
```
Expected: two non-empty files. Verify: `wc -c frontend/vendor/*.js` shows sizes > 10000.

- [ ] **Step 2: Create `frontend/index.html`**

Create `frontend/index.html`:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Indicator Dashboard</title>
  <link rel="stylesheet" href="/css/style.css" />
  <script src="/vendor/sortable.min.js" defer></script>
  <script src="/vendor/plotly.min.js" defer></script>
  <script src="/js/api.js" defer></script>
  <script src="/js/state.js" defer></script>
  <script src="/js/detail.js" defer></script>
  <script src="/js/watchlist.js" defer></script>
  <script src="/js/marketwide.js" defer></script>
  <script src="/js/settings.js" defer></script>
  <script src="/js/main.js" defer></script>
</head>
<body>
  <header class="topbar">
    <h1>Indicator Dashboard</h1>
    <button id="settings-btn" class="btn">Settings</button>
  </header>

  <main class="grid">
    <section id="watchlist-panel" class="box">
      <div class="box-head">
        <span>Watchlist</span>
        <div class="box-actions">
          <input id="add-ticker" class="mini-input" placeholder="Add ticker" />
          <button id="add-group" class="btn-sm">+ Group</button>
        </div>
      </div>
      <div id="watchlist-body" class="box-body"></div>
    </section>

    <section id="detail-panel" class="box">
      <div class="box-head">
        <span id="detail-title">Detail</span>
        <button id="add-to-watchlist" class="btn-sm" hidden>+ Add to watchlist</button>
      </div>
      <div id="detail-body" class="box-body">
        <p class="empty">Select a ticker to see its indicators.</p>
      </div>
    </section>

    <section id="marketwide-panel" class="box">
      <div class="box-head">
        <div id="marketwide-tabs" class="tabs">
          <button class="tab active" data-tab="top_buy">Top Buy</button>
          <button class="tab" data-tab="top_sell">Top Sell</button>
        </div>
        <span id="scan-status" class="scan-status"></span>
      </div>
      <div id="marketwide-body" class="box-body grid-tiles"></div>
    </section>
  </main>

  <div id="settings-modal" class="modal" hidden></div>
</body>
</html>
```

- [ ] **Step 3: Create `frontend/css/style.css`**

Create `frontend/css/style.css`:
```css
:root {
  --bg: #ffffff;
  --frame: #d9d9d9;
  --frame-strong: #bbbbbb;
  --text: #1a1a1a;
  --muted: #777;
  --sb-strong: #1a7f37; --sb: #4caf50; --sb-watch: #9ccc9a;
  --neutral: #8a8a8a;
  --ss-watch: #eba39a; --ss: #e57373; --ss-strong: #c62828;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 13px/1.4 -apple-system, Segoe UI, Roboto, sans-serif;
}
.topbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 14px; border-bottom: 1px solid var(--frame);
}
.topbar h1 { font-size: 15px; margin: 0; font-weight: 600; }

.grid {
  display: grid; gap: 10px; padding: 10px;
  grid-template-columns: 320px 1fr;
  grid-template-rows: minmax(320px, 1fr) minmax(220px, 40vh);
  grid-template-areas: "watch detail" "market market";
  height: calc(100vh - 45px);
}
#watchlist-panel { grid-area: watch; }
#detail-panel { grid-area: detail; }
#marketwide-panel { grid-area: market; }

.box {
  border: 1px solid var(--frame); background: var(--bg);
  display: flex; flex-direction: column; min-height: 0;
}
.box-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 10px; border-bottom: 1px solid var(--frame);
  font-weight: 600; background: #fafafa;
}
.box-body { padding: 8px; overflow: auto; min-height: 0; flex: 1; }
.empty { color: var(--muted); }

.btn, .btn-sm { border: 1px solid var(--frame-strong); background: #fff;
  cursor: pointer; border-radius: 0; }
.btn { padding: 4px 10px; } .btn-sm { padding: 2px 6px; font-size: 12px; }
.mini-input { border: 1px solid var(--frame-strong); padding: 2px 6px; width: 110px; }
.box-actions { display: flex; gap: 6px; }

/* Watchlist groups & rows */
.group { border: 1px solid var(--frame); margin-bottom: 8px; }
.group-head { display: flex; justify-content: space-between; align-items: center;
  padding: 4px 8px; background: #f2f2f2; cursor: pointer; font-weight: 600; }
.group-rows { padding: 2px; }
.group.collapsed .group-rows { display: none; }
.row {
  display: grid; grid-template-columns: 1fr auto auto auto auto 16px;
  gap: 6px; align-items: center; padding: 3px 6px; border: 1px solid transparent;
  cursor: pointer;
}
.row:hover { background: #f7f7f7; }
.row.selected { border-color: var(--frame-strong); background: #eef; }
.row .sym { font-weight: 600; }
.row .num { text-align: right; font-variant-numeric: tabular-nums; color: var(--muted); }
.dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.row .del { color: var(--muted); text-align: center; }

/* Marketwide tiles */
.tabs { display: flex; gap: 4px; }
.tab { border: 1px solid var(--frame-strong); background: #fff; padding: 2px 10px; cursor: pointer; }
.tab.active { background: var(--text); color: #fff; }
.scan-status { color: var(--muted); font-weight: 400; }
.grid-tiles {
  display: grid; gap: 3px;
  grid-template-columns: repeat(auto-fill, minmax(72px, 1fr));
  align-content: start;
}
.tile {
  border: 1px solid var(--frame); padding: 4px; text-align: center;
  cursor: pointer; color: #fff; font-size: 11px; line-height: 1.2;
}
.tile .tsym { font-weight: 700; }
.tile .tnum { font-variant-numeric: tabular-nums; opacity: .95; }

/* Signal colors */
.sig-strong-buy { background: var(--sb-strong); }
.sig-buy { background: var(--sb); }
.sig-watch-oversold { background: var(--sb-watch); color: #1a1a1a; }
.sig-neutral { background: var(--neutral); }
.sig-watch-overbought { background: var(--ss-watch); color: #1a1a1a; }
.sig-sell { background: var(--ss); }
.sig-strong-sell { background: var(--ss-strong); }

/* Modal */
.modal { position: fixed; inset: 0; background: rgba(0,0,0,.3);
  display: flex; align-items: center; justify-content: center; }
.modal[hidden] { display: none; }
.modal-card { background: #fff; border: 1px solid var(--frame-strong);
  padding: 16px; width: 340px; }
.modal-card label { display: flex; justify-content: space-between; margin: 6px 0; }
```

- [ ] **Step 4: Start the server and verify the shell**

Run: `./run.sh` (leave running in a terminal), then open `http://localhost:8000`.
Expected: white page, three bordered boxes in the layout (watchlist top-left, detail top-right, marketwide full-width bottom), "Top Buy/Top Sell" tabs, a Settings button. No data yet is fine. No console errors except possibly failed `/api/...` (wired next).

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/css/style.css frontend/vendor
git commit -m "feat: frontend shell + white boxed layout + vendored libs"
```

---

### Task 12: API client + shared state

**Files:**
- Create: `frontend/js/api.js`, `frontend/js/state.js`

- [ ] **Step 1: Create `frontend/js/api.js`**

Create `frontend/js/api.js`:
```javascript
const API = {
  async getWatchlist() { return (await fetch("/api/watchlist")).json(); },
  async putWatchlist(data) {
    await fetch("/api/watchlist", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },
  async getSettings() { return (await fetch("/api/settings")).json(); },
  async putSettings(data) {
    await fetch("/api/settings", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },
  async getTicker(sym) {
    const r = await fetch(`/api/ticker/${encodeURIComponent(sym)}`);
    if (!r.ok) throw new Error(`No data for ${sym}`);
    return r.json();
  },
  async getScan(tab) { return (await fetch(`/api/scan?tab=${tab}`)).json(); },
  async runScan() { await fetch("/api/scan/run", { method: "POST" }); },
};
```

- [ ] **Step 2: Create `frontend/js/state.js`**

Create `frontend/js/state.js`:
```javascript
const State = {
  watchlist: { groups: [] },
  settings: null,
  selected: null,      // currently displayed ticker symbol
  scanTab: "top_buy",
};

// Map a signal label to a CSS class.
function signalClass(signal) {
  return "sig-" + signal.toLowerCase()
    .replace(/\(|\)/g, "").trim().replace(/\s+/g, "-");
}
```

- [ ] **Step 3: Reload the page**

Reload `http://localhost:8000`.
Expected: no console errors; `API` and `State` exist (type `API` in devtools console → object).

- [ ] **Step 4: Commit**

```bash
git add frontend/js/api.js frontend/js/state.js
git commit -m "feat: frontend API client + shared state"
```

---

### Task 13: Detail panel (Plotly) + main bootstrap

**Files:**
- Create: `frontend/js/detail.js`, `frontend/js/main.js`

- [ ] **Step 1: Create `frontend/js/detail.js`**

Create `frontend/js/detail.js`:
```javascript
const Detail = {
  async show(sym) {
    State.selected = sym;
    const title = document.getElementById("detail-title");
    const body = document.getElementById("detail-body");
    const addBtn = document.getElementById("add-to-watchlist");
    title.textContent = sym + " …";
    body.innerHTML = '<p class="empty">Loading…</p>';
    let d;
    try {
      d = await API.getTicker(sym);
    } catch (e) {
      title.textContent = sym;
      body.innerHTML = `<p class="empty">No data for ${sym}.</p>`;
      return;
    }
    title.textContent = `${sym} — ${d.latest.signal} (${d.latest.price})`;
    addBtn.hidden = false;
    addBtn.dataset.sym = sym;
    body.innerHTML = '<div id="detail-chart" style="height:100%;min-height:520px"></div>';
    Detail.render(d);
    if (window.Watchlist) Watchlist.highlight(sym);
  },

  render(d) {
    const s = d.series, t = d.thresholds;
    const traces = [
      { x: s.dates, y: s.close, name: "Close", xaxis: "x", yaxis: "y" },
      { x: s.dates, y: s.wr, name: "Williams %R", xaxis: "x", yaxis: "y2" },
      { x: s.dates, y: s.rsi, name: "RSI", xaxis: "x", yaxis: "y3" },
      { x: s.dates, y: s.stochK, name: "%K", xaxis: "x", yaxis: "y4" },
      { x: s.dates, y: s.stochD, name: "%D", xaxis: "x", yaxis: "y4" },
    ];
    const hline = (yref, yval, color) => ({
      type: "line", xref: "paper", x0: 0, x1: 1, yref, y0: yval, y1: yval,
      line: { color, width: 1, dash: "dot" },
    });
    const layout = {
      showlegend: false, margin: { t: 20, r: 10, b: 20, l: 40 },
      grid: { rows: 4, columns: 1, pattern: "independent" },
      yaxis: { domain: [0.72, 1] }, yaxis2: { domain: [0.48, 0.68] },
      yaxis3: { domain: [0.24, 0.44] }, yaxis4: { domain: [0, 0.20] },
      xaxis: { anchor: "y4" },
      shapes: [
        hline("y2", t.wr_oversold, "green"), hline("y2", t.wr_overbought, "red"),
        hline("y3", t.rsi_oversold, "green"), hline("y3", t.rsi_overbought, "red"),
        hline("y4", t.stoch_oversold, "green"), hline("y4", t.stoch_overbought, "red"),
      ],
      annotations: [
        { text: "Price", x: 0, y: 1, xref: "paper", yref: "paper", showarrow: false, font: { size: 11 } },
        { text: "Williams %R", x: 0, y: 0.68, xref: "paper", yref: "paper", showarrow: false, font: { size: 11 } },
        { text: "RSI", x: 0, y: 0.44, xref: "paper", yref: "paper", showarrow: false, font: { size: 11 } },
        { text: "Stochastic", x: 0, y: 0.20, xref: "paper", yref: "paper", showarrow: false, font: { size: 11 } },
      ],
    };
    Plotly.newPlot("detail-chart", traces, layout, { displayModeBar: false, responsive: true });
  },
};
```

- [ ] **Step 2: Create `frontend/js/main.js`**

Create `frontend/js/main.js`:
```javascript
async function boot() {
  State.settings = await API.getSettings();
  await Watchlist.load();
  Marketwide.init();
  Settings.init();

  document.getElementById("add-to-watchlist").addEventListener("click", (e) => {
    const sym = e.currentTarget.dataset.sym;
    if (sym) Watchlist.addTicker(sym);
  });
}
document.addEventListener("DOMContentLoaded", boot);
```

- [ ] **Step 3: Reload and smoke-test the detail chart via console**

Reload the page, then in the devtools console run: `Detail.show("AAPL")`.
Expected: the detail box title updates to `AAPL — <signal> (<price>)`, the "+ Add to watchlist" button appears, and a 4-panel Plotly chart (Price / Williams %R / RSI / Stochastic) renders with dotted threshold lines. (Requires the server reachable and yfinance working.)

- [ ] **Step 4: Commit**

```bash
git add frontend/js/detail.js frontend/js/main.js
git commit -m "feat: detail panel with Plotly 4-panel chart + bootstrap"
```

---

### Task 14: Watchlist panel — render, select, add/delete

**Files:**
- Create: `frontend/js/watchlist.js`

- [ ] **Step 1: Create `frontend/js/watchlist.js`**

Create `frontend/js/watchlist.js`:
```javascript
const Watchlist = {
  async load() {
    State.watchlist = await API.getWatchlist();
    Watchlist.render();
    await Watchlist.refreshReadings();
  },

  async save() { await API.putWatchlist(State.watchlist); },

  render() {
    const body = document.getElementById("watchlist-body");
    body.innerHTML = "";
    State.watchlist.groups.forEach((group, gi) => {
      const g = document.createElement("div");
      g.className = "group" + (group.collapsed ? " collapsed" : "");
      g.dataset.gi = gi;

      const head = document.createElement("div");
      head.className = "group-head";
      head.innerHTML = `<span class="gname">${group.name}</span>
        <span class="gtoggle">${group.collapsed ? "▸" : "▾"}</span>`;
      head.addEventListener("click", () => {
        group.collapsed = !group.collapsed;
        Watchlist.save(); Watchlist.render(); Watchlist.refreshReadings();
      });

      const rows = document.createElement("div");
      rows.className = "group-rows";
      rows.dataset.gi = gi;
      group.tickers.forEach((sym) => rows.appendChild(Watchlist.rowEl(sym)));

      g.appendChild(head); g.appendChild(rows);
      body.appendChild(g);
    });
    if (window.Sortable) Watchlist.enableDnd();
  },

  rowEl(sym) {
    const row = document.createElement("div");
    row.className = "row" + (State.selected === sym ? " selected" : "");
    row.dataset.sym = sym;
    row.innerHTML = `
      <span class="sym">${sym}</span>
      <span class="num price"></span>
      <span class="num wr"></span>
      <span class="num rsi"></span>
      <span class="dot"></span>
      <span class="del">✕</span>`;
    row.addEventListener("click", (e) => {
      if (e.target.classList.contains("del")) { Watchlist.removeTicker(sym); return; }
      Detail.show(sym);
    });
    return row;
  },

  highlight(sym) {
    document.querySelectorAll("#watchlist-body .row").forEach((r) =>
      r.classList.toggle("selected", r.dataset.sym === sym));
  },

  async refreshReadings() {
    const syms = new Set();
    State.watchlist.groups.forEach((g) => g.tickers.forEach((t) => syms.add(t)));
    for (const sym of syms) {
      try {
        const d = await API.getTicker(sym);
        document.querySelectorAll(`#watchlist-body .row[data-sym="${sym}"]`).forEach((row) => {
          row.querySelector(".price").textContent = d.latest.price;
          row.querySelector(".wr").textContent = d.latest.wr;
          row.querySelector(".rsi").textContent = d.latest.rsi;
          const dot = row.querySelector(".dot");
          dot.style.background = getComputedStyle(document.documentElement)
            .getPropertyValue(dotVar(d.latest.signal));
        });
      } catch (e) { /* skip unreadable ticker */ }
    }
  },

  addTicker(symRaw) {
    const sym = symRaw.trim().toUpperCase();
    if (!sym) return;
    const groups = State.watchlist.groups;
    if (groups.some((g) => g.tickers.includes(sym))) { Detail.show(sym); return; }
    (groups[0] || (groups[0] = { name: "Watchlist", collapsed: false, tickers: [] }))
      .tickers.push(sym);
    Watchlist.save(); Watchlist.render(); Watchlist.refreshReadings();
    Detail.show(sym);
  },

  removeTicker(sym) {
    State.watchlist.groups.forEach((g) => {
      g.tickers = g.tickers.filter((t) => t !== sym);
    });
    Watchlist.save(); Watchlist.render(); Watchlist.refreshReadings();
  },

  addGroup() {
    const name = prompt("Group name:");
    if (!name) return;
    State.watchlist.groups.push({ name, collapsed: false, tickers: [] });
    Watchlist.save(); Watchlist.render();
  },

  enableDnd() { /* filled in Task 15 */ },
};

function dotVar(signal) {
  return {
    "Strong Buy": "--sb-strong", "Buy": "--sb", "Watch (oversold)": "--sb-watch",
    "Neutral": "--neutral", "Watch (overbought)": "--ss-watch",
    "Sell": "--ss", "Strong Sell": "--ss-strong",
  }[signal] || "--neutral";
}
```

- [ ] **Step 2: Wire the add-ticker input and add-group button in `main.js`**

In `frontend/js/main.js`, inside `boot()` after `Settings.init();`, add:
```javascript
  const addInput = document.getElementById("add-ticker");
  addInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { Watchlist.addTicker(addInput.value); addInput.value = ""; }
  });
  document.getElementById("add-group").addEventListener("click", () => Watchlist.addGroup());
```

- [ ] **Step 3: Reload and verify**

Reload `http://localhost:8000`.
Expected: the default "Watchlist" group shows AAPL and MSFT with price/%R/RSI and a colored signal dot. Clicking a row loads its chart in the detail panel and highlights the row. Typing a symbol (e.g. `NVDA`) + Enter adds it and shows it. Clicking ✕ removes a row. "+ Group" creates a new group. Reloading preserves changes (persisted).

- [ ] **Step 4: Commit**

```bash
git add frontend/js/watchlist.js frontend/js/main.js
git commit -m "feat: watchlist panel render, select, add/remove, groups"
```

---

### Task 15: Drag-and-drop reordering + grouping (SortableJS)

**Files:**
- Modify: `frontend/js/watchlist.js` (`enableDnd`)

- [ ] **Step 1: Implement `enableDnd` (replace the stub)**

In `frontend/js/watchlist.js`, replace `enableDnd() { /* filled in Task 15 */ },` with:
```javascript
  enableDnd() {
    // Reorder tickers within/between groups.
    document.querySelectorAll("#watchlist-body .group-rows").forEach((rowsEl) => {
      new Sortable(rowsEl, {
        group: "tickers", animation: 120, draggable: ".row",
        onEnd: () => Watchlist.syncFromDom(),
      });
    });
    // Reorder groups themselves.
    new Sortable(document.getElementById("watchlist-body"), {
      group: "groups", animation: 120, draggable: ".group", handle: ".group-head",
      onEnd: () => Watchlist.syncFromDom(),
    });
  },

  syncFromDom() {
    const body = document.getElementById("watchlist-body");
    const groups = [];
    body.querySelectorAll(".group").forEach((gEl) => {
      const gi = Number(gEl.dataset.gi);
      const existing = State.watchlist.groups[gi] || { name: "Group", collapsed: false };
      const tickers = [...gEl.querySelectorAll(".row")].map((r) => r.dataset.sym);
      groups.push({ name: existing.name, collapsed: existing.collapsed, tickers });
    });
    State.watchlist.groups = groups;
    Watchlist.save();
    Watchlist.render();
    Watchlist.refreshReadings();
  },
```

Note: `syncFromDom` reads group identity from the pre-move `data-gi` on each `.group` element (SortableJS moves the DOM node but keeps its dataset), so group names/collapsed state follow their moved node.

- [ ] **Step 2: Reload and verify drag/drop**

Reload the page. Create a second group ("+ Group", e.g. "Tech"). 
Expected: dragging a ticker row moves it within a group and between groups; the change persists on reload. Dragging a group by its header reorders groups; persists on reload.

- [ ] **Step 3: Commit**

```bash
git add frontend/js/watchlist.js
git commit -m "feat: drag-and-drop ticker reordering and grouping"
```

---

### Task 16: Marketwide grid + tabs + scan polling

**Files:**
- Create: `frontend/js/marketwide.js`

- [ ] **Step 1: Create `frontend/js/marketwide.js`**

Create `frontend/js/marketwide.js`:
```javascript
const Marketwide = {
  pollTimer: null,

  init() {
    document.querySelectorAll("#marketwide-tabs .tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll("#marketwide-tabs .tab")
          .forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        State.scanTab = tab.dataset.tab;
        Marketwide.refresh();
      });
    });
    Marketwide.refresh();
    Marketwide.poll();
  },

  async refresh() {
    const data = await API.getScan(State.scanTab);
    Marketwide.renderStatus(data);
    Marketwide.renderTiles(data.rows);
  },

  renderStatus(data) {
    const el = document.getElementById("scan-status");
    if (data.scanning) { el.textContent = "Scanning…"; return; }
    if (!data.scanned_at) { el.textContent = "No scan yet"; return; }
    const when = new Date(data.scanned_at);
    el.textContent = "Last scan: " + when.toLocaleString();
  },

  renderTiles(rows) {
    const body = document.getElementById("marketwide-body");
    body.innerHTML = "";
    rows.forEach((r) => {
      const tile = document.createElement("div");
      tile.className = "tile " + signalClass(r.signal);
      tile.innerHTML = `<div class="tsym">${r.ticker}</div>
        <div class="tnum">${r.price}</div>`;
      tile.title = `${r.signal} · %R ${r.wr} · RSI ${r.rsi} · %K ${r.stochK}`;
      tile.addEventListener("click", () => Detail.show(r.ticker));
      body.appendChild(tile);
    });
  },

  poll() {
    // While a scan is running, refresh every 3s until it finishes.
    Marketwide.pollTimer = setInterval(async () => {
      const data = await API.getScan(State.scanTab);
      Marketwide.renderStatus(data);
      if (!data.scanning && data.rows.length) {
        Marketwide.renderTiles(data.rows);
      }
    }, 3000);
  },
};
```

- [ ] **Step 2: Reload and verify the marketwide grid**

Reload `http://localhost:8000`. If this is the first run, the status shows "Scanning…" then "Last scan: …" once the background scan finishes (seed universe is tiny, so this is fast; the full universe takes a couple of minutes).
Expected: a dense grid of signal-colored tiles (symbol + price). Clicking "Top Sell" reorders them (most overbought first); "Top Buy" reorders back. Clicking a tile loads that ticker in the detail panel. Hover shows a tooltip with the readings.

- [ ] **Step 3: Commit**

```bash
git add frontend/js/marketwide.js
git commit -m "feat: marketwide grid, tabs, and scan status polling"
```

---

### Task 17: Settings modal (thresholds + lookback)

**Files:**
- Create: `frontend/js/settings.js`

- [ ] **Step 1: Create `frontend/js/settings.js`**

Create `frontend/js/settings.js`:
```javascript
const Settings = {
  init() {
    document.getElementById("settings-btn")
      .addEventListener("click", Settings.open);
  },

  open() {
    const s = State.settings;
    const t = s.thresholds;
    const modal = document.getElementById("settings-modal");
    modal.hidden = false;
    modal.innerHTML = `
      <div class="modal-card">
        <h3>Settings</h3>
        <label>Lookback
          <select id="set-lookback">
            ${["3mo","6mo","1y","2y"].map((o) =>
              `<option ${o===s.lookback?"selected":""}>${o}</option>`).join("")}
          </select>
        </label>
        ${Settings.numRow("wr_oversold","Williams %R oversold",t)}
        ${Settings.numRow("wr_overbought","Williams %R overbought",t)}
        ${Settings.numRow("rsi_oversold","RSI oversold",t)}
        ${Settings.numRow("rsi_overbought","RSI overbought",t)}
        ${Settings.numRow("stoch_oversold","Stochastic oversold",t)}
        ${Settings.numRow("stoch_overbought","Stochastic overbought",t)}
        <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
          <button class="btn" id="set-cancel">Cancel</button>
          <button class="btn" id="set-save">Save</button>
        </div>
      </div>`;
    modal.querySelector("#set-cancel").onclick = () => { modal.hidden = true; };
    modal.querySelector("#set-save").onclick = Settings.save;
  },

  numRow(key, label, t) {
    return `<label>${label}
      <input type="number" id="set-${key}" value="${t[key]}" style="width:80px" /></label>`;
  },

  async save() {
    const modal = document.getElementById("settings-modal");
    const s = State.settings;
    s.lookback = modal.querySelector("#set-lookback").value;
    ["wr_oversold","wr_overbought","rsi_oversold","rsi_overbought",
     "stoch_oversold","stoch_overbought"].forEach((k) => {
      s.thresholds[k] = Number(modal.querySelector(`#set-${k}`).value);
    });
    await API.putSettings(s);
    modal.hidden = true;
    // Re-derive everything that depends on thresholds/lookback.
    await Watchlist.refreshReadings();
    if (State.selected) Detail.show(State.selected);
    Marketwide.refresh();
  },
};
```

- [ ] **Step 2: Reload and verify settings**

Reload the page, click "Settings".
Expected: a modal with a lookback dropdown and six threshold number inputs prefilled from current settings. Change RSI oversold to 25, Save. The modal closes; watchlist signal dots, the detail chart threshold lines, and the marketwide ranking all update to reflect the new threshold. Reload → the change persisted.

- [ ] **Step 3: Commit**

```bash
git add frontend/js/settings.js
git commit -m "feat: settings modal for thresholds and lookback"
```

---

## PHASE 5 — Full universe, cleanup, docs

### Task 18: Populate full constituent lists

**Files:**
- Modify: `backend/constituents/sp500.txt`, `backend/constituents/nasdaq100.txt`

- [ ] **Step 1: Replace seed lists with full membership**

Populate `sp500.txt` with the full current S&P 500 tickers (one per line, yfinance format — e.g. `BRK-B`, `BF-B`) and `nasdaq100.txt` with the full Nasdaq-100 tickers. Source from the current Wikipedia constituent tables at implementation time.

- [ ] **Step 2: Verify the universe size**

Run: `./.venv/bin/python -c "from backend.universe import load_universe; u=load_universe(); print(len(u))"`
Expected: roughly 560–580 unique tickers.

- [ ] **Step 3: Run a real scan end-to-end (network)**

With the server running, click a tab / wait for the startup scan. Alternatively:
Run: `curl -s -X POST http://localhost:8000/api/scan/run` then `curl -s "http://localhost:8000/api/scan?tab=top_buy" | ./.venv/bin/python -m json.tool | head`
Expected: a couple of minutes to complete; `rows` populated with hundreds of names, each with a signal. Some tickers may be skipped (reported as absent) — acceptable.

- [ ] **Step 4: Commit**

```bash
git add backend/constituents/sp500.txt backend/constituents/nasdaq100.txt
git commit -m "feat: full S&P 500 + Nasdaq-100 constituent lists"
```

---

### Task 19: Remove legacy Streamlit app, update README

**Files:**
- Delete: `app.py`
- Modify: `README.md`

- [ ] **Step 1: Remove the legacy Streamlit entrypoint**

Run: `git rm app.py`
Expected: `app.py` staged for deletion. (History retains it via the initial commit.)

- [ ] **Step 2: Rewrite `README.md`**

Replace `README.md` with:
```markdown
# Indicator Dashboard

A local web dashboard tracking a grouped watchlist against three momentum
oscillators — Williams %R, RSI, and Stochastic %K/%D — plus a marketwide
scanner over the S&P 500 + Nasdaq-100. You check it on your own schedule.

## Setup

1. Python 3.10+ and a virtualenv:
   ```
   python3 -m venv .venv
   ./.venv/bin/pip install -r requirements.txt
   ```
2. Run:
   ```
   ./run.sh
   ```
   Open http://localhost:8000.

## Layout

- **Left — Watchlist:** create named groups, drag tickers to reorder/regroup,
  click a ticker to inspect it. Persists to `watchlist.json`.
- **Right — Detail:** price + Williams %R + RSI + Stochastic charts with your
  threshold lines.
- **Bottom — Marketwide:** a dense grid of ~570 S&P 500 + Nasdaq-100 names,
  ranked by the tab (Top Buy / Top Sell). Click a tile to inspect it.
- **Settings:** thresholds + lookback window, applied to both the watchlist and
  the marketwide ranking. Persists to `settings.json`.

## The marketwide scan

Daily bars, so the scan runs once per day after the US close. It runs when you
open the app if that day's scan hasn't happened yet, and again after the close
while the app is open. Nothing runs while the app is closed. Results cache to
`scan_cache.json`. It does not run on market holidays' schedules specifically —
at worst an unnecessary scan runs on a holiday.

## Notes and limitations

- Price data is Yahoo Finance via `yfinance` (unofficial). If tickers stop
  loading, try `./.venv/bin/pip install --upgrade yfinance`.
- Signal *surfacing*, not trading advice. Nothing places trades.
- Constituent lists are static files under `backend/constituents/`; update them
  manually when membership changes.
- No automated alerts by design — you check in manually.
```

- [ ] **Step 3: Verify the full test suite still passes**

Run: `./.venv/bin/pytest`
Expected: PASS (all tests green; nothing imported `app.py`).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove legacy Streamlit app, rewrite README for web app"
```

---

### Task 20: Final end-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Full suite**

Run: `./.venv/bin/pytest`
Expected: all green.

- [ ] **Step 2: Cold start**

Run: `./run.sh`, open http://localhost:8000 fresh.
Expected: watchlist loads with readings; selecting a ticker renders the 4-panel chart; groups/drag-drop/add/remove work and persist; marketwide grid fills after the scan; tabs reorder; tile click opens detail; settings changes propagate and persist.

- [ ] **Step 3: Confirm watchlist migration happened**

Run: `./.venv/bin/python -c "import json; print(json.load(open('watchlist.json')))"`
Expected: grouped structure `{"groups": [...]}` (migrated from the original flat list).

- [ ] **Step 4: Tag the milestone**

```bash
git tag v2-web-app
git log --oneline | head -25
```

---

## Self-Review Notes (author checklist — already applied)

- **Spec coverage:** framework (Tasks 9–13), universe S&P500+Nasdaq100 (Tasks 6/18), daily-after-close scan + refresh-on-open + timer (Tasks 8/10/16), named groups + drag/drop (Tasks 14/15), tile→detail (Task 16), thresholds in settings applied to both watchlist and marketwide (Tasks 4/17, ranking Task 2), white boxed layout (Task 11), auto-migration (Task 3), Plotly detail (Task 13). All spec sections map to a task.
- **Refinement vs spec:** the scan cache stores *raw readings* only; `signal`/`score`/`magnitude` are computed at `/api/scan` request time so threshold changes re-rank without rescanning (spec §7.2 listed them in-cache; this is a deliberate, documented improvement).
- **Type/name consistency:** `classify_signal(wr, rsi, stochK, thresholds)`, `rank_rows(rows, thresholds, tab)`, threshold keys (`wr_oversold`…`stoch_overbought`), row keys (`ticker/price/wr/rsi/stochK`), and signal→CSS mapping (`signalClass`) are consistent across backend and frontend.
- **No placeholders:** every code step contains full content; the two constituent `.txt` files are intentionally seeded small in Task 6 and completed in Task 18.
```
