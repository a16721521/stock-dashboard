# Dashboard Redesign — Design Spec

**Date:** 2026-08-14
**Status:** Approved for planning
**Supersedes:** the current single-file Streamlit app (`app.py`)

## 1. Summary

Rebuild the local trading dashboard from a Streamlit app into a **custom local
web app** with a three-region layout: a left **watchlist** panel (grouped,
drag-orderable tickers), a right **detail** panel (indicator charts for the
selected ticker), and a bottom full-width **marketwide** panel (a dense,
tab-ranked grid scanning the S&P 500 + Nasdaq-100).

The existing indicator and signal logic is reused essentially unchanged. What
changes is the delivery: a Python JSON backend plus a hand-written HTML/CSS/JS
frontend, replacing Streamlit so the app can deliver drag-and-drop grouping, a
dense marketwide grid, and a custom all-white boxed aesthetic that Streamlit
cannot render cleanly.

## 2. Motivation

The desired interface — drag-to-reorder tickers, user-defined groups,
click-to-highlight selection, a tight grid of hundreds of stocks, and an
all-white rectangular-boxed three-panel layout — is beyond what Streamlit
renders gracefully. Each of those features fights Streamlit's rerun model and
theming. A thin custom web app gives full layout control while reusing all the
data and indicator code that already works.

## 3. Stack

- **Backend:** FastAPI (Python), served by uvicorn. Owns yfinance fetching, the
  indicator/signal math, the marketwide scan cache, and the scheduler. Reuses
  the existing `williams_r`, `rsi`, `stochastic`, `build_indicator_frame`, and
  `classify_signal` functions with minimal change (extracted into a module).
- **Frontend:** Plain HTML/CSS/JS with **no build step**. No React/Node
  toolchain.
  - Drag-and-drop reordering/grouping via **SortableJS** (single vendored JS
    file, no package manager).
  - Detail-panel charts via **Plotly.js** (vendored), matching the quality of
    the current Streamlit Plotly charts.
- **Run:** one command. A small launcher (`run.sh` or equivalent) starts
  uvicorn and the app is used at `http://localhost:8000`. The existing `.venv`
  is reused; `requirements.txt` gains `fastapi` and `uvicorn`, keeps
  `yfinance`/`pandas`/`numpy`, and drops `streamlit` and the Python `plotly`
  (charting moves to browser-side Plotly.js).

Rationale for no framework/build step: this is a single-user local tool; a build
toolchain adds friction with no payoff at this scale.

## 4. Layout & Aesthetic

**Aesthetic:** light theme, white background, thin 1px gray borders framing
every region and every grid tile, sharp corners, a clean compact sans-serif for
data density. Signal colors (the existing green→red scale) are the only strong
color in the interface.

**Regions:**

```
┌────────────┬───────────────────────────────┐
│ WATCHLIST  │  DETAIL (selected ticker)      │
│ (groups,   │  price + Williams %R + RSI +   │
│  drag/drop)│  Stochastic, threshold lines   │
├────────────┴───────────────────────────────┤
│ MARKETWIDE   [Top Buy][Top Sell][ + … ]     │
│ tight grid of ~570 tiles, ranked by tab     │
└─────────────────────────────────────────────┘
```

Top row is two columns (watchlist left, detail right). Bottom is a full-width
panel. Each region is a bordered box.

## 5. Panels

### 5.1 Left — Watchlist

- **Named groups** the user creates, renames, collapses/expands, reorders, and
  deletes.
- Tickers can be dragged to reorder within a group and moved between groups.
- Tickers can be added (input) and deleted.
- Each ticker row shows: symbol, its current signal color, and compact readings
  (Price, %R, RSI, %K).
- Clicking a ticker highlights it and loads it into the Detail panel.
- State persists to disk (see §7).

### 5.2 Right — Detail

- Shows the selected item's price chart plus three indicator charts (Williams
  %R, RSI, Stochastic %K/%D), each with the active threshold lines drawn —
  functionally the current Streamlit detail view, rebuilt in Plotly.js.
- Works identically whether the selection came from a watchlist ticker or a
  marketwide grid tile.
- Includes an **"+ Add to watchlist"** action (adds the currently displayed
  ticker to a chosen group).

### 5.3 Bottom — Marketwide

- A dense grid of the ~570 unique S&P 500 + Nasdaq-100 names.
- Each tile: symbol, signal-colored background, and the tile's rank metric.
- **Tabs above the grid reorder it:** `Top Buy` and `Top Sell` to start. The
  tab set is structured (a list of named ranking views) so additional tabs can
  be added later without rework.
- Clicking a tile loads that ticker into the Detail panel (does **not**
  auto-add it to the watchlist).

## 6. Thresholds & Settings

- Thresholds remain adjustable and drive every signal. They live in a small
  **settings area** (gear), not the main layout.
- Defaults match the current app: Williams %R −80/−20, RSI 30/70, Stochastic
  20/80.
- Threshold values apply to **both** the watchlist signals and the marketwide
  ranking, consistently.
- Settings (thresholds + lookback window) persist to disk.

## 7. Data & Persistence

Two JSON files in the project folder.

### 7.1 `watchlist.json` (schema change, auto-migrated)

Evolves from a flat list to grouped structure:

```json
{
  "groups": [
    { "name": "Watchlist", "collapsed": false, "tickers": ["AAPL", "MSFT"] }
  ]
}
```

On first run, an existing flat-list `watchlist.json`
(e.g. `["AAPL","MSFT"]`) is auto-migrated into a single default group named
"Watchlist". Migration is one-way and idempotent (already-migrated files are
left as-is).

### 7.2 `scan_cache.json`

```json
{
  "scanned_at": "2026-08-14T20:05:00-04:00",
  "universe": "sp500+nasdaq100",
  "rows": [
    { "ticker": "AAPL", "price": 305.93, "wr": -86.1, "rsi": 43.8,
      "stochK": 10.6, "signal": "Buy", "score": 2, "rank_metric": 1.83 }
  ]
}
```

### 7.3 `settings.json`

Persists thresholds (six values) and the lookback window. Created with defaults
on first run if absent.

## 8. Marketwide Scan & Scheduler

- **Universe:** static bundled constituent lists for the S&P 500 and Nasdaq-100
  (~570 unique after dedup), stored in the repo. (Lists are updated manually
  when constituents change; not fetched live.)
- **Fetching:** yfinance batched downloads in chunks (multiple symbols per
  call) rather than ~570 individual requests, to stay fast and avoid
  rate-limiting. Symbols returning empty/thin data are skipped and reported.
- **Cadence:** once per trading day, after US market close (~4pm ET), when daily
  bars are final.
- **Mechanism (no OS-level job):**
  - On app launch, if today's post-close scan has not yet run, run it, showing a
    progress indicator; otherwise load the cache.
  - While the app is running, an in-app timer triggers the scan after the
    close.
  - Nothing runs while the app is closed. Fresh data is guaranteed whenever the
    user opens the app.

## 9. Ranking Logic (tab ordering)

- **Primary key:** the existing integer signal score
  (Strong Buy = +3 … Neutral = 0 … Strong Sell = −3).
- **Tiebreak within a tier:** a **composite magnitude** = the sum of each
  indicator's normalized distance past its threshold. This surfaces the *most*
  oversold/overbought names first rather than an arbitrary order.
  - For an oversold indicator: how far below its oversold threshold, normalized
    to the threshold's available range.
  - For an overbought indicator: how far above its overbought threshold,
    normalized similarly.
- **`Top Buy`** sorts descending by (score, composite oversold magnitude);
  **`Top Sell`** sorts by (−score, composite overbought magnitude).
- `rank_metric` in the cache stores the composite magnitude so the frontend can
  render tiles without recomputation.

## 10. Backend API (indicative)

- `GET  /api/watchlist` → grouped watchlist structure.
- `PUT  /api/watchlist` → save full grouped structure (reorder / rename / add /
  remove / move / collapse).
- `GET  /api/ticker/{symbol}` → indicator series + latest readings + signal for
  the Detail panel, computed with current thresholds/lookback.
- `GET  /api/scan` → cached marketwide rows + `scanned_at`.
- `POST /api/scan/run` → trigger a scan now (used for initial/forced runs);
  returns progress/result.
- `GET/PUT /api/settings` → thresholds + lookback.

Exact shapes are finalized during planning/implementation.

## 11. Testing

- **Unit — indicators/signal:** the reused math functions get unit tests against
  known fixtures (the pipeline was already smoke-tested against live data;
  values like AAPL %R −86.1 / RSI 43.8 / %K 10.6 are a reference sanity point).
- **Unit — ranking:** given synthetic rows + thresholds, assert `Top Buy` /
  `Top Sell` ordering and `rank_metric`.
- **Unit — watchlist migration:** flat list → grouped structure; idempotency on
  already-migrated files.
- **API:** endpoint tests with yfinance mocked (no network in test).
- **Frontend:** manual/smoke verification in-browser (drag/drop, selection, tab
  switching, scan progress); no heavy frontend test harness for a local tool.

## 12. Build Order (incremental phases)

1. Backend skeleton: extract indicators into a module, `/api/ticker`, watchlist
   load + auto-migration, `/api/watchlist`.
2. Frontend shell: white boxed three-region layout; Left + Right panels working
   (select ticker → Detail renders).
3. Groups + drag/drop (SortableJS) with persistence.
4. Marketwide scan + `scan_cache.json` + bottom grid + tabs + tile→Detail.
5. Scheduler (refresh-on-open-if-stale + in-app timer).
6. Settings area (thresholds/lookback) + aesthetic polish pass.

## 13. Out of Scope (YAGNI)

- No automated alerts/notifications (unchanged design principle).
- No OS-level scheduled job (launchd); scan is app-lifetime only.
- No live-fetched constituent lists; bundled static lists updated manually.
- No accounts, no deployment, no multi-user — single local user only.
- No intraday bars; daily bars only, as today.

## 14. Decisions Log

- Framework: **custom local web app** (not Streamlit, not React).
- Marketwide universe: **S&P 500 + Nasdaq-100** (~570 unique).
- Scan cadence: **once daily after close**.
- Scan mechanism: **refresh-on-open + in-app timer**, no OS job.
- Grouping: **user-created named groups**.
- Marketwide tile click: **load into Detail panel** (not auto-add).
- Thresholds: **kept, in a settings area**, applied to watchlist + marketwide.
