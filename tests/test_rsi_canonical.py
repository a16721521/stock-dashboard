"""Authoritative Wilder RSI tests with hand-computed values.

Canonical Wilder RSI seeds the first average gain/loss with the arithmetic mean
of the first `period` changes, then applies the recursive smoothing
avg = (avg_prev*(period-1) + current) / period. This differs from a plain
ewm(adjust=False), which seeds from the first value and weights recent bars
more heavily near the start of the series.
"""

import numpy as np
import pandas as pd
import pytest

from backend.indicators import rsi


def _df(closes):
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="B")
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1,
                         "Close": c, "Volume": np.ones(len(c))}, index=idx)


def test_wilder_seed_value_is_exactly_50():
    # 7 gains of +1 then 7 losses of -1 => seed avg_gain == avg_loss == 0.5 => RSI 50
    closes = [100, 101, 102, 103, 104, 105, 106, 107, 106, 105, 104, 103, 102, 101, 100]
    r = rsi(_df(closes), period=14)
    assert r.iloc[14] == pytest.approx(50.0)


def test_wilder_recursive_step():
    # After the seed (0.5/0.5), a +2 change gives:
    # avg_gain = (0.5*13 + 2)/14 = 8.5/14 ; avg_loss = (0.5*13 + 0)/14 = 6.5/14
    # rs = 8.5/6.5 ; RSI = 100 - 100/(1+rs) = 56.6667
    closes = [100, 101, 102, 103, 104, 105, 106, 107, 106, 105, 104, 103, 102, 101, 100, 102]
    r = rsi(_df(closes), period=14)
    assert r.iloc[15] == pytest.approx(56.6667, abs=1e-3)


def test_flat_series_is_50_not_nan():
    # constant price => all gains and losses zero => RSI 50 (was NaN under old impl)
    r = rsi(_df([100.0] * 20), period=14)
    assert r.iloc[-1] == pytest.approx(50.0)


def test_all_up_is_100():
    r = rsi(_df(list(range(100, 130))), period=14)
    assert r.iloc[-1] == pytest.approx(100.0)


def test_all_down_is_0():
    r = rsi(_df(list(range(130, 100, -1))), period=14)
    assert r.iloc[-1] == pytest.approx(0.0)


def test_range_bounds():
    rng = np.random.default_rng(0)
    closes = 100 + np.cumsum(rng.normal(0, 1, 200))
    r = rsi(_df(closes), period=14).dropna()
    assert (r >= 0).all() and (r <= 100).all()
