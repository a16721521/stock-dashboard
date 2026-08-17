from backend.indicators import DEFAULT_THRESHOLDS
from backend.ranking import oversold_magnitude, overbought_magnitude, rank_rows


def test_oversold_magnitude_deep_is_near_two():
    # wr=-100 (max), rsi=0 -> both fully past oversold thresholds -> 2.0
    m = oversold_magnitude(-100, 0, DEFAULT_THRESHOLDS)
    assert 1.9 <= m <= 2.0


def test_oversold_magnitude_none_is_zero():
    m = oversold_magnitude(-50, 50, DEFAULT_THRESHOLDS)
    assert m == 0.0


def test_overbought_magnitude_extreme_is_near_two():
    m = overbought_magnitude(0, 100, DEFAULT_THRESHOLDS)
    assert 1.9 <= m <= 2.0


def test_rank_rows_most_oversold_orders_deepest_first():
    rows = [
        {"ticker": "A", "price": 1, "wr": -50, "rsi": 50, "stochK": 50},    # neutral
        {"ticker": "B", "price": 1, "wr": -100, "rsi": 5, "stochK": 5},     # deeply oversold
        {"ticker": "C", "price": 1, "wr": -85, "rsi": 25, "stochK": 50},    # oversold, shallow
    ]
    out = rank_rows(rows, DEFAULT_THRESHOLDS, "most_oversold")
    assert [r["ticker"] for r in out] == ["B", "C", "A"]
    assert out[0]["state"] == "Deeply Oversold"
    assert out[0]["research_status"] == "Observation"


def test_rank_rows_most_overbought_orders_extreme_first():
    rows = [
        {"ticker": "A", "price": 1, "wr": -50, "rsi": 50, "stochK": 50},
        {"ticker": "B", "price": 1, "wr": 0, "rsi": 95, "stochK": 95},      # deeply overbought
        {"ticker": "C", "price": 1, "wr": -15, "rsi": 75, "stochK": 50},    # overbought
    ]
    out = rank_rows(rows, DEFAULT_THRESHOLDS, "most_overbought")
    assert [r["ticker"] for r in out] == ["B", "C", "A"]
    assert out[0]["state"] == "Deeply Overbought"


def test_rank_rows_default_tab_is_most_oversold():
    rows = [{"ticker": "B", "price": 1, "wr": -100, "rsi": 5, "stochK": 5}]
    out = rank_rows(rows, DEFAULT_THRESHOLDS, "anything_else")
    assert out[0]["state"] == "Deeply Oversold"
