import numpy as np
import pandas as pd

from backend.indicators import (
    williams_r, rsi, stochastic, build_indicator_frame,
    DEFAULT_THRESHOLDS,
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


def test_williams_r_equals_100_plus_raw_stoch_k(ohlc):
    # Identity: raw Stochastic %K == 100 + Williams %R over the same window.
    # (This is why Stochastic is not counted as an independent factor.)
    wr = williams_r(ohlc)
    low = ohlc["Low"].rolling(14).min()
    high = ohlc["High"].rolling(14).max()
    raw_k = (ohlc["Close"] - low) / (high - low) * 100
    diff = (raw_k - (100 + wr)).dropna()
    assert diff.abs().max() < 1e-9
