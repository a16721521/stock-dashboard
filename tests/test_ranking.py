from backend.indicators import DEFAULT_THRESHOLDS
from backend.ranking import oversold_magnitude, overbought_magnitude, rank_rows


def test_oversold_magnitude_deep_is_near_three():
    # wr=-100 (max), rsi=0, stoch=0 → all three fully past oversold thresholds
    m = oversold_magnitude(-100, 0, 0, DEFAULT_THRESHOLDS)
    assert 2.9 <= m <= 3.0


def test_oversold_magnitude_none_is_zero():
    m = oversold_magnitude(-50, 50, 50, DEFAULT_THRESHOLDS)
    assert m == 0.0


def test_overbought_magnitude_extreme_is_near_three():
    m = overbought_magnitude(0, 100, 100, DEFAULT_THRESHOLDS)
    assert 2.9 <= m <= 3.0


def test_rank_rows_top_buy_orders_most_oversold_first():
    rows = [
        {"ticker": "A", "price": 1, "wr": -50, "rsi": 50, "stochK": 50},   # neutral
        {"ticker": "B", "price": 1, "wr": -100, "rsi": 5, "stochK": 5},    # strong buy, deep
        {"ticker": "C", "price": 1, "wr": -85, "rsi": 25, "stochK": 50},   # buy, shallow
    ]
    out = rank_rows(rows, DEFAULT_THRESHOLDS, "top_buy")
    assert [r["ticker"] for r in out] == ["B", "C", "A"]
    assert out[0]["signal"] == "Strong Buy"


def test_rank_rows_top_sell_orders_most_overbought_first():
    rows = [
        {"ticker": "A", "price": 1, "wr": -50, "rsi": 50, "stochK": 50},
        {"ticker": "B", "price": 1, "wr": 0, "rsi": 95, "stochK": 95},
        {"ticker": "C", "price": 1, "wr": -15, "rsi": 75, "stochK": 50},
    ]
    out = rank_rows(rows, DEFAULT_THRESHOLDS, "top_sell")
    assert [r["ticker"] for r in out] == ["B", "C", "A"]
    assert out[0]["signal"] == "Strong Sell"
