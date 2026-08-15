"""Marketwide ranking: how far past threshold each name is, and tab ordering."""

from backend.indicators import classify_signal


def _clamp01(x):
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def oversold_magnitude(wr, rsi_val, stoch_k, t):
    """Sum of normalized distances *below* each oversold threshold, in [0, 3]."""
    wr_term = _clamp01((t["wr_oversold"] - wr) / (t["wr_oversold"] - (-100)))
    rsi_term = _clamp01((t["rsi_oversold"] - rsi_val) / t["rsi_oversold"])
    stoch_term = _clamp01((t["stoch_oversold"] - stoch_k) / t["stoch_oversold"])
    return wr_term + rsi_term + stoch_term


def overbought_magnitude(wr, rsi_val, stoch_k, t):
    """Sum of normalized distances *above* each overbought threshold, in [0, 3]."""
    wr_term = _clamp01((wr - t["wr_overbought"]) / (0 - t["wr_overbought"]))
    rsi_term = _clamp01((rsi_val - t["rsi_overbought"]) / (100 - t["rsi_overbought"]))
    stoch_term = _clamp01((stoch_k - t["stoch_overbought"]) / (100 - t["stoch_overbought"]))
    return wr_term + rsi_term + stoch_term


def rank_rows(rows, thresholds, tab):
    """Return rows enriched with signal/score/magnitude, sorted for the tab.

    tab: "top_buy" (most oversold first) or "top_sell" (most overbought first).
    """
    enriched = []
    for r in rows:
        signal, score = classify_signal(r["wr"], r["rsi"], r["stochK"], thresholds)
        if tab == "top_sell":
            magnitude = overbought_magnitude(r["wr"], r["rsi"], r["stochK"], thresholds)
            sort_key = (-score, magnitude)
        else:  # top_buy default
            magnitude = oversold_magnitude(r["wr"], r["rsi"], r["stochK"], thresholds)
            sort_key = (score, magnitude)
        enriched.append({**r, "signal": signal, "score": score,
                         "magnitude": round(magnitude, 3), "_sort": sort_key})
    enriched.sort(key=lambda r: r["_sort"], reverse=True)
    for r in enriched:
        del r["_sort"]
    return enriched
