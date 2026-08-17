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
- `FINDINGS.md` — results and interpretation from `feature_screen.py`'s most
  recent run. Its one surviving result (12-1 month momentum) is followed up
  properly in `momentum_screen.py` below.
- `momentum_screen.py` — a deeper, methodology-appropriate follow-up on
  momentum specifically: monthly decile-sort portfolio spreads (the way the
  effect was originally discovered) over 10 years, instead of daily IC over
  5. Same caveat discipline as `feature_screen.py`.
- `MOMENTUM_FINDINGS.md` — results and interpretation from `momentum_screen.py`.
- `output/` — the raw run logs and CSVs behind both findings docs.

Run: `./.venv/bin/python research/feature_screen.py` or
`./.venv/bin/python research/momentum_screen.py` (both need network access
for the yfinance fetch; each takes under a minute).
