"""Marketwide ranking over two factors (Williams %R range position + RSI).

Ranking orders by factual state score, tie-broken by how far past threshold the
two factors are. Stochastic is not a ranking factor (see indicators.classify_state).
Tabs: "most_oversold" and "most_overbought" — factual, not buy/sell.
"""

from backend.indicators import classify_state


def _clamp01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def oversold_magnitude(wr, rsi_val, t):
    """Sum of normalized distances below the two oversold thresholds, in [0, 2]."""
    wr_term = _clamp01((t["wr_oversold"] - wr) / (t["wr_oversold"] - (-100)))
    rsi_term = _clamp01((t["rsi_oversold"] - rsi_val) / t["rsi_oversold"])
    return wr_term + rsi_term


def overbought_magnitude(wr, rsi_val, t):
    """Sum of normalized distances above the two overbought thresholds, in [0, 2]."""
    wr_term = _clamp01((wr - t["wr_overbought"]) / (0 - t["wr_overbought"]))
    rsi_term = _clamp01((rsi_val - t["rsi_overbought"]) / (100 - t["rsi_overbought"]))
    return wr_term + rsi_term


def rank_rows(rows, thresholds, tab):
    """Return rows enriched with state/score/research_status/magnitude, sorted.

    tab: "most_oversold" (default) or "most_overbought".
    """
    enriched = []
    for r in rows:
        cls = classify_state(r["wr"], r["rsi"], thresholds)
        if tab == "most_overbought":
            magnitude = overbought_magnitude(r["wr"], r["rsi"], thresholds)
            sort_key = (-cls["score"], magnitude)
        else:  # most_oversold
            magnitude = oversold_magnitude(r["wr"], r["rsi"], thresholds)
            sort_key = (cls["score"], magnitude)
        enriched.append({**r, "state": cls["state"], "score": cls["score"],
                         "research_status": cls["research_status"],
                         "magnitude": round(magnitude, 3), "_sort": sort_key})
    enriched.sort(key=lambda r: r["_sort"], reverse=True)
    for r in enriched:
        del r["_sort"]
    return enriched
