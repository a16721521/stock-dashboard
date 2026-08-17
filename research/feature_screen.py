"""Cheap feature/IC screen — a go/no-go smoke test, NOT strategy validation.

Purpose
-------
Before investing weeks in the full research pipeline (walk-forward training,
calibration, model registry, point-in-time data acquisition), check cheaply
whether ANY of the candidate features from the strategy proposal carry real
information about forward returns. If nothing here shows a non-trivial,
stable information coefficient, the expensive build isn't worth starting on
this feature set.

What this deliberately is NOT
------------------------------
- NOT point-in-time. Universe = current S&P 500 + Nasdaq-100 membership
  applied to the full lookback window, so it is survivorship-biased (today's
  winners are being tested on their own past). A real backtest needs
  historical index membership; this script does not have it.
- NOT walk-forward. Every date's cross-sectional IC uses the full available
  history; there's no train/test separation. This is fine for "is there any
  signal at all" but not for "how much" or "would this have been tradable".
- NOT cost-aware. Returns are gross, no spread/slippage/commission.
- NOT a backtest. No positions, no portfolio, no Sharpe ratio. Just: does
  ranking stocks by feature X on day t correlate with their forward return?

Method
------
For each candidate feature and each forward-return target, compute the
day-by-day cross-sectional Spearman rank correlation (the standard
"Information Coefficient" from Grinold & Kahn's Active Portfolio Management),
then look at the distribution of that daily IC across ~4 years of trading
days: mean, standard deviation, and a t-stat for whether the mean is
distinguishable from zero.

Two t-stats are reported for the 5- and 20-day horizons:
  - "naive": using every trading day. Overlapping-window forward returns are
    autocorrelated day to day, so this overstates significance.
  - "non-overlapping": using every h-th day only, which removes most of that
    overlap at the cost of a much smaller, noisier sample. Treat this as the
    more honest (if conservative) number.

A secondary regime split re-runs the reversal features' IC separately in
high- vs low-market-volatility days and above- vs below-200dma days, to test
whether reversal is conditional on regime (the Nagel "compensation for
liquidity provision" hypothesis) rather than a flat, always-on effect —
which the dashboard's live diagnostics already showed no evidence of.

Run: ./.venv/bin/python research/feature_screen.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.data import fetch_batch, fetch_history  # noqa: E402
from backend.indicators import williams_r, rsi  # noqa: E402
from backend.universe import load_universe  # noqa: E402

LOOKBACK_PERIOD = "5y"
BENCHMARK = "SPY"
MIN_NAMES_PER_DAY = 50   # skip cross-sections too thin to trust
HORIZONS = [1, 5, 20]


def build_ticker_panel(ticker, df, spy_fwd):
    """One ticker's OHLCV -> a date-indexed DataFrame of features + forward
    returns (raw and market-adjusted)."""
    close = df["Close"]
    vol = df["Volume"]
    log_ret_1 = np.log(close / close.shift(1))

    feats = pd.DataFrame(index=df.index)
    feats["wr"] = williams_r(df)
    feats["rsi"] = rsi(df)
    feats["rev_5"] = -np.log(close / close.shift(5))        # + = recent drop
    feats["ret_21"] = close.pct_change(21)
    feats["ret_63"] = close.pct_change(63)
    feats["ret_126"] = close.pct_change(126)
    feats["mom_12_1"] = np.log(close.shift(21) / close.shift(252))
    feats["dist_20dma"] = close / close.rolling(20).mean() - 1
    feats["dist_50dma"] = close / close.rolling(50).mean() - 1
    feats["trend_200"] = close / close.rolling(200).mean() - 1
    feats["vol_20"] = log_ret_1.rolling(20).std() * np.sqrt(252)
    feats["dollar_vol_20"] = (close * vol).rolling(20).median()

    # Forward returns: signal at close(t), entry approximated at close(t+1)
    # (a real system would use next-session OPEN; close is an engineering
    # approximation acceptable for a screen, not for a tradable backtest).
    for h in HORIZONS:
        raw_fwd = np.log(close.shift(-(1 + h)) / close.shift(-1))
        feats[f"fwd_ret_{h}"] = raw_fwd
        feats[f"fwd_ret_{h}_mkt"] = raw_fwd - spy_fwd[h].reindex(feats.index)

    feats["ticker"] = ticker
    return feats


def compute_spy_context(spy_df):
    """SPY-derived series used for market-adjustment and regime splits."""
    close = spy_df["Close"]
    log_ret_1 = np.log(close / close.shift(1))
    fwd = {}
    for h in HORIZONS:
        fwd[h] = np.log(close.shift(-(1 + h)) / close.shift(-1))
    vol_20 = log_ret_1.rolling(20).std() * np.sqrt(252)
    above_200dma = close > close.rolling(200).mean()
    high_vol = vol_20 > vol_20.median()   # in-sample median split (screen only)
    return fwd, above_200dma, high_vol


def daily_ic(panel, feature_cols, target_cols, min_names=MIN_NAMES_PER_DAY):
    """Day-by-day cross-sectional Spearman IC for every feature x target pair.
    Returns a long DataFrame: date, feature, target, ic."""
    records = []
    cols = feature_cols + target_cols
    for date, group in panel.groupby(panel.index):
        if len(group) < min_names:
            continue
        corr = group[cols].corr(method="spearman")
        for f in feature_cols:
            for t in target_cols:
                val = corr.loc[f, t]
                if pd.notna(val):
                    records.append((date, f, t, val))
    return pd.DataFrame(records, columns=["date", "feature", "target", "ic"])


def summarize_ic(ic_long, horizon_of):
    """mean/std/n/t-stat per (feature,target), plus a non-overlapping
    subsample t-stat for horizons > 1 day."""
    rows = []
    for (feature, target), g in ic_long.groupby(["feature", "target"]):
        g = g.sort_values("date")
        h = horizon_of[target]
        mean_ic = g["ic"].mean()
        std_ic = g["ic"].std(ddof=1)
        n = len(g)
        t_naive = mean_ic / std_ic * np.sqrt(n) if std_ic > 0 else np.nan

        sub = g.iloc[::h] if h > 1 else g
        mean_sub, std_sub, n_sub = sub["ic"].mean(), sub["ic"].std(ddof=1), len(sub)
        t_sub = mean_sub / std_sub * np.sqrt(n_sub) if std_sub > 0 and n_sub > 1 else np.nan

        rows.append({
            "feature": feature, "target": target, "horizon": h,
            "mean_ic": mean_ic, "n_days": n, "t_stat_naive": t_naive,
            "mean_ic_nonoverlap": mean_sub, "n_nonoverlap": n_sub,
            "t_stat_nonoverlap": t_sub,
        })
    return pd.DataFrame(rows)


def conditional_ic(panel, feature_cols, target_cols, regime_series, regime_name,
                    min_names=MIN_NAMES_PER_DAY):
    """Re-run daily_ic separately on the True and False halves of a per-date
    boolean regime split (e.g. high-vol vs low-vol days)."""
    regime_by_date = regime_series.reindex(panel.index.unique())
    rows = []
    for label, want in [("high", True), ("low", False)]:
        dates = regime_by_date[regime_by_date == want].index
        sub_panel = panel[panel.index.isin(dates)]
        ic = daily_ic(sub_panel, feature_cols, target_cols, min_names=min_names)
        for (feature, target), g in ic.groupby(["feature", "target"]):
            mean_ic, std_ic, n = g["ic"].mean(), g["ic"].std(ddof=1), len(g)
            t = mean_ic / std_ic * np.sqrt(n) if std_ic > 0 and n > 1 else np.nan
            rows.append({"regime": regime_name, "level": label, "feature": feature,
                        "target": target, "mean_ic": mean_ic, "n_days": n, "t_stat": t})
    return pd.DataFrame(rows)


def main():
    t0 = time.time()
    universe = load_universe()
    print(f"Universe: {len(universe)} tickers (current membership — "
          f"survivorship-biased). Fetching {LOOKBACK_PERIOD} of history "
          f"(batched)...")

    spy_df = fetch_history(BENCHMARK, LOOKBACK_PERIOD)
    if spy_df is None:
        print("FATAL: could not fetch SPY benchmark data.")
        sys.exit(1)
    spy_fwd, spy_above_200dma, spy_high_vol = compute_spy_context(spy_df)

    frames = fetch_batch(universe, LOOKBACK_PERIOD)
    print(f"Fetched {len(frames)}/{len(universe)} tickers "
          f"in {time.time() - t0:.1f}s. Building feature panel...")

    panels = []
    for ticker, df in frames.items():
        if len(df) < 260:   # need a full year+ for 252-day momentum warmup
            continue
        panels.append(build_ticker_panel(ticker, df, spy_fwd))
    panel = pd.concat(panels)
    print(f"Panel: {len(panel):,} ticker-days across {len(panels)} tickers, "
          f"{panel.index.min().date()} to {panel.index.max().date()}.")

    feature_cols = ["wr", "rsi", "rev_5", "ret_21", "ret_63", "ret_126",
                    "mom_12_1", "dist_20dma", "dist_50dma", "trend_200",
                    "vol_20", "dollar_vol_20"]
    target_cols = [f"fwd_ret_{h}{suffix}"
                   for h in HORIZONS for suffix in ("", "_mkt")]
    horizon_of = {f"fwd_ret_{h}{suffix}": h
                  for h in HORIZONS for suffix in ("", "_mkt")}

    print("Computing daily cross-sectional IC "
          f"({len(feature_cols)} features x {len(target_cols)} targets)...")
    ic_long = daily_ic(panel, feature_cols, target_cols)
    summary = summarize_ic(ic_long, horizon_of)

    # Regime-conditional check on the reversal-family features only: does
    # reversal IC concentrate in high-vol / risk-off days (Nagel's
    # liquidity-provision hypothesis), rather than being flat/always-on?
    reversal_feats = ["wr", "rsi", "rev_5"]
    mkt_targets = [f"fwd_ret_{h}_mkt" for h in HORIZONS]
    print("Computing regime-conditional IC for reversal features...")
    cond_vol = conditional_ic(panel, reversal_feats, mkt_targets,
                              spy_high_vol, "market_vol_20d")
    cond_trend = conditional_ic(panel, reversal_feats, mkt_targets,
                                spy_above_200dma, "spy_above_200dma")
    conditional = pd.concat([cond_vol, cond_trend], ignore_index=True)

    print(f"\nDone in {time.time() - t0:.1f}s total.\n")
    return panel, ic_long, summary, conditional, feature_cols


if __name__ == "__main__":
    panel, ic_long, summary, conditional, feature_cols = main()

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)
    summary["_abs_t"] = summary["t_stat_nonoverlap"].abs()
    summary.sort_values(["target", "_abs_t"], ascending=[True, False]) \
        .drop(columns="_abs_t").to_csv(out_dir / "ic_summary.csv", index=False)

    pd.set_option("display.width", 160)
    pd.set_option("display.max_rows", 200)
    print("=" * 100)
    print("UNCONDITIONAL IC (all days) — sorted by |non-overlapping t-stat| within each target")
    print("=" * 100)
    for target in [f"fwd_ret_{h}{s}" for h in HORIZONS for s in ("", "_mkt")]:
        sub = summary[summary["target"] == target].copy()
        sub = sub.reindex(sub["t_stat_nonoverlap"].abs().sort_values(ascending=False).index)
        print(f"\n--- target = {target} ---")
        print(sub[["feature", "mean_ic", "n_days", "t_stat_naive",
                   "mean_ic_nonoverlap", "n_nonoverlap", "t_stat_nonoverlap"]]
              .to_string(index=False, float_format=lambda x: f"{x:0.4f}"))

    conditional.to_csv(out_dir / "ic_conditional.csv", index=False)
    print("\n" + "=" * 100)
    print("CONDITIONAL IC — reversal features, split by market regime "
          "(market-adjusted targets only)")
    print("=" * 100)
    for (regime, target), g in conditional.groupby(["regime", "target"]):
        print(f"\n--- regime = {regime}, target = {target} ---")
        print(g[["feature", "level", "mean_ic", "n_days", "t_stat"]]
              .sort_values(["feature", "level"])
              .to_string(index=False, float_format=lambda x: f"{x:0.4f}"))

    print(f"\nFull results written to {out_dir / 'ic_summary.csv'} "
          f"and {out_dir / 'ic_conditional.csv'}")
