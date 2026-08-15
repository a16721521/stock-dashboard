import numpy as np
import pandas as pd

from backend.indicators import (
    williams_r, rsi, stochastic, build_indicator_frame,
    classify_signal, DEFAULT_THRESHOLDS,
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


def test_classify_all_oversold_is_strong_buy():
    t = DEFAULT_THRESHOLDS
    label, score = classify_signal(-90, 20, 10, t)
    assert label == "Strong Buy" and score == 3


def test_classify_all_overbought_is_strong_sell():
    t = DEFAULT_THRESHOLDS
    label, score = classify_signal(-10, 80, 90, t)
    assert label == "Strong Sell" and score == -3


def test_classify_neutral():
    t = DEFAULT_THRESHOLDS
    label, score = classify_signal(-50, 50, 50, t)
    assert label == "Neutral" and score == 0
