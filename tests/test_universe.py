from backend.universe import load_universe


def test_universe_is_deduped_and_sorted():
    u = load_universe()
    assert "AAPL" in u
    assert "TSLA" in u          # nasdaq-only seed
    assert "JPM" in u           # sp500-only seed
    assert len(u) == len(set(u))  # no duplicates
    assert u == sorted(u)
