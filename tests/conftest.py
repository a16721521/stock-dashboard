import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def ohlc():
    """Deterministic 60-day OHLC frame with a clear downtrend then bounce,
    enough rows for 14-period indicators to be non-NaN at the tail."""
    n = 60
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    # Falling then rising close, with High/Low bracketing it.
    close = np.concatenate([np.linspace(100, 60, 40), np.linspace(60, 75, 20)])
    high = close + 1.5
    low = close - 1.5
    open_ = close + 0.2
    vol = np.full(n, 1_000_000)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol},
        index=idx,
    )
