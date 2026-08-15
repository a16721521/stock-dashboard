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
- **Bottom — Marketwide:** a dense grid of ~500 S&P 500 + Nasdaq-100 names,
  ranked by the tab (Top Buy / Top Sell). Click a tile to inspect it.
- **Settings:** thresholds + lookback window, applied to both the watchlist and
  the marketwide ranking. Persists to `settings.json`.

## The marketwide scan

Daily bars, so the scan runs once per day after the US close. It runs when you
open the app if that day's scan hasn't happened yet, and again after the close
while the app is open. Nothing runs while the app is closed. Results cache to
`scan_cache.json`. Market holidays are not modelled specifically — at worst an
unnecessary scan runs on a holiday.

## Notes and limitations

- Price data is Yahoo Finance via `yfinance` (unofficial). If tickers stop
  loading, try `./.venv/bin/pip install --upgrade yfinance`.
- Signal *surfacing*, not trading advice. Nothing places trades.
- Ticker symbols use Yahoo's format (e.g. `BRK-B`, not `BRKB` or `BRK.B`).
  A symbol Yahoo doesn't recognize shows blank readings and is skipped.
- Constituent lists are static files under `backend/constituents/`; update them
  manually when membership changes.
- No automated alerts by design — you check in manually.

## Code layout

- `backend/` — FastAPI app (`app.py`) plus focused modules: `indicators`,
  `ranking`, `data`, `watchlist`, `settings`, `universe`, `scan`, `scheduler`.
- `frontend/` — no-build HTML/CSS/JS; SortableJS + Plotly.js vendored.
- `tests/` — pytest suite (`./.venv/bin/pytest`); network is always mocked.
