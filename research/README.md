# research/

Offline, exploratory scripts — **not** part of the live dashboard app. Nothing
here is imported by `backend/` or `frontend/`; it's read-only analysis against
already-fetched market data, run manually.

- `feature_screen.py` — a cheap feature/information-coefficient smoke test.
  Run before investing in the full walk-forward research/backtesting
  pipeline, to check cheaply whether any candidate feature carries real
  forward-return information. See its module docstring for method and
  explicit caveats (survivorship-biased, not walk-forward, not cost-aware,
  not a backtest).
- `FINDINGS.md` — results and interpretation from the most recent run.
- `output/` — the raw run log and CSVs behind `FINDINGS.md`.

Run: `./.venv/bin/python research/feature_screen.py` (needs network access
for the yfinance fetch; takes under a minute).
