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
