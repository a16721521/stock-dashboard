"""Indicator math and signal classification — plain pandas, no TA library."""

import math

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


def _wilder_average(series, period):
    """SMA-seeded Wilder recursive moving average.

    `series` has a leading NaN (from .diff()). The seed at position `period` is
    the arithmetic mean of the first `period` changes (positions 1..period);
    thereafter avg[t] = (avg[t-1] * (period - 1) + series[t]) / period.
    """
    vals = series.to_numpy(dtype=float)
    n = len(vals)
    out = np.full(n, np.nan)
    if n <= period:
        return pd.Series(out, index=series.index)
    prev = float(np.nanmean(vals[1:period + 1]))
    out[period] = prev
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + vals[i]) / period
        out[i] = prev
    return pd.Series(out, index=series.index)


def rsi(df, period=14):
    """Canonical Wilder RSI. Edge cases: no movement -> 50, only gains -> 100,
    only losses -> 0."""
    delta = df["Close"].diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = _wilder_average(gain, period)
    avg_loss = _wilder_average(loss, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        out = 100.0 - (100.0 / (1.0 + rs))
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    only_gain = (avg_loss == 0) & (avg_gain > 0)
    out = out.where(~both_zero, 50.0)    # no movement -> neutral
    out = out.where(~only_gain, 100.0)   # only gains -> 100 (avoid inf)
    return out


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


# ---------------------------------------------------------------------------
# Factual state classification (agreement + depth over Williams %R and RSI).
#
# Stochastic is deliberately excluded as a third vote: raw Stochastic %K equals
# 100 + Williams %R and the smoothed %K is ~0.95 correlated with Williams %R, so
# counting it would be double-counting the same range-position information.
# These are factual oscillator states, NOT trade recommendations.
# ---------------------------------------------------------------------------

RESEARCH_STATUS_DEFAULT = "Observation"

STATE_SCORE = {
    "Deeply Oversold": 3, "Oversold": 2, "Mildly Oversold": 1,
    "Neutral": 0, "Mixed": 0, "Invalid": 0,
    "Mildly Overbought": -1, "Overbought": -2, "Deeply Overbought": -3,
}


def _finite(x):
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


def _deep_thresholds(t):
    """Deep sub-thresholds: the midpoint from the normal threshold to the
    extreme of each oscillator's range."""
    return {
        "wr_os": (t["wr_oversold"] + (-100.0)) / 2.0,
        "wr_ob": t["wr_overbought"] / 2.0,
        "rsi_os": t["rsi_oversold"] / 2.0,
        "rsi_ob": (t["rsi_overbought"] + 100.0) / 2.0,
    }


def classify_state(wr, rsi_val, t):
    """Return {state, score, research_status} for a Williams %R + RSI pair.

    A directional family (oversold/overbought) requires BOTH factors to agree.
    If they disagree -> "Mixed". Depth ("Deeply"/plain/"Mildly") reflects how
    far past threshold both factors are. Missing/non-finite inputs -> "Invalid".
    """
    if not _finite(wr) or not _finite(rsi_val):
        return {"state": "Invalid", "score": 0,
                "research_status": RESEARCH_STATUS_DEFAULT}

    d = _deep_thresholds(t)
    wr_os = wr <= t["wr_oversold"]
    wr_ob = wr >= t["wr_overbought"]
    rsi_os = rsi_val <= t["rsi_oversold"]
    rsi_ob = rsi_val >= t["rsi_overbought"]
    n_os = int(wr_os) + int(rsi_os)
    n_ob = int(wr_ob) + int(rsi_ob)

    if n_os and n_ob:                    # one factor each side -> conflict
        state = "Mixed"
    elif n_os == 2:
        both_deep = wr <= d["wr_os"] and rsi_val <= d["rsi_os"]
        state = "Deeply Oversold" if both_deep else "Oversold"
    elif n_os == 1:
        state = "Mildly Oversold"
    elif n_ob == 2:
        both_deep = wr >= d["wr_ob"] and rsi_val >= d["rsi_ob"]
        state = "Deeply Overbought" if both_deep else "Overbought"
    elif n_ob == 1:
        state = "Mildly Overbought"
    else:
        state = "Neutral"

    return {"state": state, "score": STATE_SCORE[state],
            "research_status": RESEARCH_STATUS_DEFAULT}
