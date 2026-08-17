"""State classifier: agreement + depth over two factors (Williams %R, RSI).

Stochastic is intentionally NOT a third vote (it is ~0.95 correlated with
Williams %R). Deep sub-thresholds are the midpoint from the normal threshold to
the extreme, so with defaults: RSI deep-oversold 15, deep-overbought 85;
Williams %R deep-oversold -90, deep-overbought -10.
"""

import numpy as np

from backend.indicators import classify_state, DEFAULT_THRESHOLDS as T


def s(wr, rsi):
    return classify_state(wr, rsi, T)["state"]


def test_deeply_oversold_needs_both_deep():
    assert s(-95, 10) == "Deeply Oversold"


def test_oversold_both_past_normal_not_deep():
    assert s(-82, 25) == "Oversold"


def test_mildly_oversold_one_factor_only():
    assert s(-85, 50) == "Mildly Oversold"   # WR oversold, RSI neutral


def test_neutral():
    assert s(-50, 50) == "Neutral"


def test_mildly_overbought_one_factor_only():
    assert s(-10, 50) == "Mildly Overbought"  # WR overbought, RSI neutral


def test_overbought_both_past_normal():
    assert s(-15, 75) == "Overbought"


def test_deeply_overbought_needs_both_deep():
    assert s(-5, 90) == "Deeply Overbought"


def test_conflict_is_mixed_not_branch_order():
    # The 3.4 bug case: WR oversold, RSI overbought. Must NOT silently pick one.
    assert s(-90, 80) == "Mixed"


def test_boundary_values_count_as_past():
    # exactly at threshold: WR == -80 and RSI == 30 -> both oversold (<=)
    assert s(-80, 30) == "Oversold"


def test_invalid_on_missing_or_nonfinite():
    assert s(None, 30) == "Invalid"
    assert s(-90, None) == "Invalid"
    assert s(np.nan, 30) == "Invalid"
    assert s(-90, float("inf")) == "Invalid"


def test_scores_are_signed_by_depth():
    assert classify_state(-95, 10, T)["score"] == 3
    assert classify_state(-82, 25, T)["score"] == 2
    assert classify_state(-85, 50, T)["score"] == 1
    assert classify_state(-50, 50, T)["score"] == 0
    assert classify_state(-5, 90, T)["score"] == -3
    assert classify_state(-90, 80, T)["score"] == 0     # Mixed is not a ranking side


def test_research_status_is_observation():
    assert classify_state(-95, 10, T)["research_status"] == "Observation"
