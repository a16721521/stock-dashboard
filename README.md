# Indicator Dashboard

A local **observation** dashboard tracking a grouped watchlist against two
ranking factors — Williams %R and RSI — plus a marketwide scanner over the
S&P 500 + Nasdaq-100. It reports factual oscillator states (e.g. "Deeply
Oversold"), not trade recommendations: nothing here has been validated as
predictive, so nothing is labeled Buy/Sell. You check it on your own schedule.

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
- **Right — Detail:** price + Williams %R + RSI + Stochastic charts, a
  decision-summary strip (state, data freshness, research status — always
  "Observation"), and threshold lines.
- **Bottom — Marketwide:** a dense grid of ~500 S&P 500 + Nasdaq-100 names.
  Tabs: **Most Oversold**, **Most Overbought**, and **Data Problems** (scan
  freshness, coverage, and configuration status). Click a tile to inspect it —
  the detail view then shows both the reading it was ranked with and the
  current reading, and flags if they've diverged.
- **Settings:** a gear icon opens sliders for the six oscillator thresholds
  (grouped into *ranking factors* — Williams %R and RSI, which drive both the
  watchlist states and the marketwide ranking — and *chart overlay only* —
  Stochastic, which is not a ranking factor; see below) plus the lookback
  window. Persists to `settings.json`.

### Why Stochastic doesn't count toward ranking

Raw Stochastic %K is mathematically `100 + Williams %R` over the same window,
and the smoothed version stays ~0.95 correlated with it. Counting both as
independent signals would double-count the same information, so only
Williams %R and RSI drive the Observation state and the marketwide ranking.
Stochastic is still plotted and still has adjustable threshold lines — those
just affect the chart overlay, not what gets ranked.

## The marketwide scan

Daily bars, so a scan is only worth running once a session's data is final.
Freshness is judged against a real NYSE trading calendar (holidays, early
closes, and a settlement delay after the close), not a plain weekday clock —
so a scan that's technically "recent" but still shows yesterday's bar is
correctly treated as stale and retried, rather than accepted just because its
fetch timestamp is new.

- Runs when you open the app if the cache doesn't yet contain the expected
  finalized session, and again on an interval while the app stays open.
  Nothing runs while the app is closed.
- A scan only replaces the cache if it fetched at least ~90% of the universe;
  below that (or on a completely failed fetch) the previous good cache is
  left untouched. The **Data Problems** tab and the status strip on every
  marketwide/detail view show both the **last successful** scan and the
  **last attempt** — so a failed refresh stays visible instead of silently
  vanishing behind an unchanged "last known good" cache.
- The cache also records what it was computed under (lookback, algorithm
  version, universe). Changing the lookback makes the existing cache
  **incompatible** until a fresh scan completes — you'll see a "rescan
  pending" notice rather than stale numbers presented as current. Changing
  thresholds does *not* require a rescan, since ranking is recomputed live
  from the cached raw readings.
- Results cache to `scan_cache.json`; the most recent attempt (successful or
  not) is recorded separately in `scan_last_attempt.json`.

## Notes and limitations

- Price data is Yahoo Finance via `yfinance` (unofficial). If tickers stop
  loading, try `./.venv/bin/pip install --upgrade yfinance`.
- Observation only, not trading advice. Nothing here places trades or claims
  a validated edge.
- Ticker symbols use Yahoo's format (e.g. `BRK-B`, not `BRKB` or `BRK.B`).
  A symbol Yahoo doesn't recognize shows blank readings and is skipped.
- Constituent lists are static files under `backend/constituents/`, reflecting
  **current** index membership — update them manually when membership
  changes. This makes them survivorship-biased; fine for day-to-day
  observation, not sound as evidence for historical backtesting.
- `settings.json` is validated on every load, not just on save — a hand-edited
  or otherwise invalid file falls back to safe defaults and is preserved
  alongside as `settings.invalid.json` for inspection, rather than being
  silently used (which could crash the ranking math on out-of-range values).
- No automated alerts by design — you check in manually.

## Code layout

- `backend/` — FastAPI app (`app.py`) plus focused modules: `indicators`,
  `ranking`, `data`, `watchlist`, `settings`, `universe`, `scan`,
  `market_calendar`, `scheduler`.
- `frontend/` — no-build HTML/CSS/JS; SortableJS + Plotly.js vendored.
- `tests/` — pytest suite (`./.venv/bin/pytest`); network is always mocked.
