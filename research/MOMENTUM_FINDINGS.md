# Momentum Decile-Sort Screen — Findings (2026-08-17)

**What this is:** a deeper, purpose-built follow-up to `feature_screen.py`'s
one surviving result (12-1 month momentum, t=3.42 at a 1-day horizon on 5
years of data). That result was tested with the wrong instrument — momentum
is a monthly-formation, monthly-to-quarterly-holding effect, and the daily
test starved longer horizons of power (only 50 independent 20-day windows in
5 years). This script uses the methodology the effect was actually
discovered with (Jegadeesh & Titman 1993): rank into deciles by 12-1
momentum at each month-end, hold an equal-weighted top-minus-bottom-decile
spread, over 10 years for more independent observations.

**Answer: directionally right, not statistically significant, real tail risk.**

## Run

- Universe: current S&P 500 + Nasdaq-100, 514/518 tickers, 10 years
  (2016-08 to 2026-08), 60,359 ticker-months
- Formation: `mom_12_1 = log(P[t-21mo]/P[t-12mo])`, monthly, decile sort
  (top vs bottom of ~500 names each month)
- Held for 1 month (108 independent, non-overlapping formations) and 3
  months (36 independent formations via non-overlapping subsample)

Full numbers: `output/momentum_run.log`, `output/momentum_summary.csv`,
per-series spread histories in `output/momentum_spread_*.csv`.

## Results

| hold | n (independent) | mean spread | std | t-stat | win rate |
|---|---|---|---|---|---|
| 1 month  | 108 | +0.90%/month   | 6.63%  | **1.41** | 56.5% |
| 3 months | 36  | +2.15%/quarter | 10.41% | **1.24** | 58.3% |

(Raw and market-adjusted spreads are numerically identical to 1e-16 — a
verified mathematical identity, not a bug: subtracting the same month's SPY
return from both legs of a long-short spread cancels exactly, so this
particular check can't distinguish raw from market-neutral. Not a
meaningful test of "is this a market-neutral effect" — it's guaranteed by
construction.)

Neither horizon clears the conventional |t| > 2 bar, let alone the stricter
3.0 Harvey-Liu-Zhu bar for a new effect. The sign is right (winners beat
losers) and the win rate is modestly above 50%, consistent with the
direction the momentum literature would predict — but on this specific
10-year window and this specific (survivorship-biased) universe, it is not
statistically distinguishable from noise. **This is a real downgrade from
the earlier daily-IC screen's t=3.42** — that number doesn't survive being
tested the way the effect is supposed to be tested. Worth stating plainly:
the more appropriate, more powerful test came back weaker, not stronger.

## Tail risk is the standout finding, not the average

The worst single-month spread in 10 years was **-25.5%, in June 2026** — the
most recent month in the sample. The next-worst was -18.5% (December 2022).
Both dwarf the average monthly gain of +0.9%: one bad month like June 2026
erases roughly 28 months of average expected return. This matches the
"Momentum Crashes" literature (Daniel & Moskowitz) cited in the original
strategy proposal — momentum has a heavy, sudden left tail, typically around
sharp market reversals — and it isn't a footnote here, it's the single
largest number in the entire result set. A momentum strategy run without
explicit crash protection (volatility scaling, drawdown limits) would be
exposed to exactly this kind of event.

## Caveats (same discipline as feature_screen.py)

- Survivorship-biased: current membership applied retroactively.
- Not sector-adjusted: an open question whether this spread is a broad
  cross-sectional effect or concentrated in mega-cap tech outperformance
  over this specific window — not resolved here.
- Not cost-aware: monthly full-decile rebalancing (~50 names each side) has
  real turnover cost, unmodeled.
- Not walk-forward: no train/test split, no out-of-sample holdout.
- No multiple-testing correction beyond what's already been spent across
  `feature_screen.py`'s 90 tests and this screen's 4 (2 horizons × 2 targets,
  though the 2 targets are identical by construction, so really 2
  meaningfully distinct tests).

## Recommendation

Momentum on this universe is a "maybe, not a yes." The direction and rough
magnitude are consistent with 30+ years of academic evidence elsewhere, which
counts for something as a prior — but this specific test, on this specific
data, doesn't clear a significance bar, and the one clear, unambiguous
finding is that the tail risk is severe and recent. I would not proceed to
the full point-in-time-data-acquisition + walk-forward + calibration build on
this evidence. If there's continued interest, the next cheap step (still well
short of the full pipeline) would be: (a) get more history if the data
source allows it — 10 years is genuinely not that many independent monthly
observations for this kind of test, academic momentum studies typically use
several decades; (b) add sector-relative momentum to check the effect isn't
just a concentration artifact; (c) look specifically at what happened in
June 2026 before treating this as a viable candidate at all.
