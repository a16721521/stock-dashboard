"""Momentum decile-sort screen — deeper follow-up to feature_screen.py.

Why a separate script, not another row in feature_screen.py
-------------------------------------------------------------
feature_screen.py tested momentum with the wrong instrument for the job: a
daily cross-sectional IC against short (1/5/20-day) forward returns. Its one
surviving result (mom_12_1, t=3.42) was only genuinely non-overlapping at the
1-day horizon — but classic 12-1 month momentum (Jegadeesh & Titman 1993) is
a monthly-formation, monthly-to-quarterly-holding effect, not a daily one.
Testing it on daily granularity with 5 years of data starved the longer
horizons of statistical power: the 20-day non-overlap check only had 50
independent windows.

This script uses the methodology the effect was actually discovered with:
rank stocks into deciles by 12-1 momentum at each month-end, hold an
equal-weighted long-short (top decile minus bottom decile) spread for the
following month (and, separately, quarter), and look at the distribution of
that spread across ~10 years of independent, non-overlapping monthly
formations. This trades away granularity for the statistical power the
effect needs to be judged fairly.

What this deliberately is NOT (same caveats as feature_screen.py)
--------------------------------------------------------------------
- NOT point-in-time (current S&P 500 + Nasdaq-100 membership, survivorship-
  biased).
- NOT walk-forward, NOT cost-aware (no spread/slippage/commission, and
  monthly rebalancing of a full decile portfolio has real turnover cost that
  is not modeled here at all).
- NOT sector-adjusted. A raw momentum spread can partly just be "mega-cap
  tech beat everything" over this specific 2016-2026 window rather than a
  broad cross-sectional effect — flagged as an open question, not resolved
  here.
- NOT a backtest. No position sizing, no portfolio simulation.

Run: ./.venv/bin/python research/momentum_screen.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.data import fetch_batch, fetch_history  # noqa: E402
from backend.universe import load_universe  # noqa: E402

LOOKBACK_PERIOD = "10y"
BENCHMARK = "SPY"
MIN_NAMES_PER_MONTH = 100
N_DECILES = 10
HOLD_MONTHS = [1, 3]


def monthly_series(df):
    """Ticker OHLCV -> month-end-sampled (mom_12_1, close) DataFrame."""
    close = df["Close"]
    mom_12_1 = np.log(close.shift(21) / close.shift(252))
    monthly = pd.DataFrame({"mom_12_1": mom_12_1, "close": close}) \
        .resample("ME").last()
    return monthly


def build_panel(frames, spy_monthly):
    rows = []
    for ticker, df in frames.items():
        if len(df) < 260:
            continue
        m = monthly_series(df)
        m["ticker"] = ticker
        rows.append(m)
    panel = pd.concat(rows)
    panel = panel.join(spy_monthly[["close"]].rename(columns={"close": "spy_close"}))
    return panel


def add_forward_returns(panel, hold_months):
    """Per-ticker forward log return over `hold_months` calendar months,
    raw and market-adjusted, computed within each ticker's own time series."""
    out = []
    for ticker, g in panel.groupby("ticker"):
        g = g.sort_index().copy()
        for h in hold_months:
            g[f"fwd_ret_{h}m"] = np.log(g["close"].shift(-h) / g["close"])
            g[f"fwd_ret_{h}m_mkt"] = (
                np.log(g["close"].shift(-h) / g["close"])
                - np.log(g["spy_close"].shift(-h) / g["spy_close"])
            )
        out.append(g)
    return pd.concat(out)


def decile_spreads(panel, target_col, min_names=MIN_NAMES_PER_MONTH):
    """For each month-end, rank by mom_12_1 into deciles, compute the
    equal-weighted top-minus-bottom-decile forward-return spread.
    Returns a Series indexed by formation month."""
    spreads = {}
    counts = {}
    for date, g in panel.groupby(panel.index):
        g = g.dropna(subset=["mom_12_1", target_col])
        if len(g) < min_names:
            continue
        g = g.copy()
        g["decile"] = pd.qcut(g["mom_12_1"], N_DECILES, labels=False, duplicates="drop")
        by_decile = g.groupby("decile")[target_col].mean()
        if by_decile.index.min() != 0 or by_decile.index.max() != N_DECILES - 1:
            continue   # qcut collapsed deciles (too few distinct values); skip
        spreads[date] = by_decile.loc[N_DECILES - 1] - by_decile.loc[0]
        counts[date] = len(g)
    s = pd.Series(spreads).sort_index()
    n = pd.Series(counts).sort_index()
    return s, n


def summarize_spread(spread, stride=1):
    """t-stat etc for a spread series, optionally subsampled every `stride`
    formations for non-overlapping holds longer than 1 month."""
    sub = spread.iloc[::stride] if stride > 1 else spread
    mean_, std_, n = sub.mean(), sub.std(ddof=1), len(sub)
    t = mean_ / std_ * np.sqrt(n) if std_ > 0 and n > 1 else np.nan
    win_rate = (sub > 0).mean()
    return {
        "n_months": n, "mean_monthly_spread_pct": mean_ * 100,
        "std_monthly_spread_pct": std_ * 100, "t_stat": t,
        "win_rate": win_rate,
        "worst_5": sub.nsmallest(5).round(4).to_dict(),
        "best_5": sub.nlargest(5).round(4).to_dict(),
    }


def main():
    t0 = time.time()
    universe = load_universe()
    print(f"Universe: {len(universe)} tickers (current membership — "
          f"survivorship-biased). Fetching {LOOKBACK_PERIOD} of history "
          f"(batched)...")

    spy_df = fetch_history(BENCHMARK, LOOKBACK_PERIOD)
    if spy_df is None:
        print("FATAL: could not fetch SPY.")
        sys.exit(1)
    spy_monthly = monthly_series(spy_df)

    frames = fetch_batch(universe, LOOKBACK_PERIOD)
    print(f"Fetched {len(frames)}/{len(universe)} tickers "
          f"in {time.time() - t0:.1f}s. Building monthly panel...")

    panel = build_panel(frames, spy_monthly)
    panel = add_forward_returns(panel, HOLD_MONTHS)
    print(f"Panel: {len(panel):,} ticker-months across "
          f"{panel['ticker'].nunique()} tickers, "
          f"{panel.index.min().date()} to {panel.index.max().date()}.")

    results = {}
    for h in HOLD_MONTHS:
        for suffix, label in [("", "raw"), ("_mkt", "mkt_adj")]:
            target = f"fwd_ret_{h}m{suffix}"
            spread, names_per_month = decile_spreads(panel, target)
            overlap_summary = summarize_spread(spread, stride=1)
            nonoverlap_summary = summarize_spread(spread, stride=h) if h > 1 else overlap_summary
            results[(h, label)] = {
                "target": target, "spread_series": spread,
                "names_per_month": names_per_month,
                "overlap": overlap_summary, "nonoverlap": nonoverlap_summary,
            }

    print(f"\nDone in {time.time() - t0:.1f}s total.\n")
    return panel, results


if __name__ == "__main__":
    panel, results = main()

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)

    print("=" * 100)
    print("MOMENTUM DECILE SPREAD (top decile minus bottom decile, equal-weighted, "
          "monthly formation)")
    print("=" * 100)
    rows_for_csv = []
    for (h, label), r in results.items():
        s = r["nonoverlap"]
        print(f"\n--- hold={h}mo, target={label} "
              f"({'non-overlapping subsample' if h > 1 else 'monthly, non-overlapping by construction'}) ---")
        print(f"  n_months={s['n_months']}  "
              f"mean_spread={s['mean_monthly_spread_pct']:.3f}%/period  "
              f"std={s['std_monthly_spread_pct']:.3f}%  "
              f"t_stat={s['t_stat']:.3f}  win_rate={s['win_rate']:.1%}")
        print(f"  worst 5 formations: {s['worst_5']}")
        print(f"  best 5 formations:  {s['best_5']}")
        rows_for_csv.append({
            "hold_months": h, "target": label,
            "n_months_overlap": r["overlap"]["n_months"],
            "t_stat_overlap": r["overlap"]["t_stat"],
            "mean_spread_pct_overlap": r["overlap"]["mean_monthly_spread_pct"],
            "n_months_nonoverlap": s["n_months"],
            "t_stat_nonoverlap": s["t_stat"],
            "mean_spread_pct_nonoverlap": s["mean_monthly_spread_pct"],
            "win_rate_nonoverlap": s["win_rate"],
        })
        r["spread_series"].rename("spread").to_csv(
            out_dir / f"momentum_spread_{h}mo_{label}.csv")

    pd.DataFrame(rows_for_csv).to_csv(out_dir / "momentum_summary.csv", index=False)
    print(f"\nFull results written to {out_dir / 'momentum_summary.csv'} "
          f"and per-series momentum_spread_*.csv files")
