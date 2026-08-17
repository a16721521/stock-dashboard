# Feature/IC Screen — Findings (2026-08-17)

**What this is:** a cheap go/no-go smoke test (see `feature_screen.py` docstring
for full method and caveats), run before committing to the multi-week
research/backtesting build proposed for turning the dashboard's oscillator
states into probability/expected-return/Buy-Sell output. Question: does *any*
candidate feature carry real forward-return information, before spending
weeks on point-in-time data, walk-forward infrastructure, and calibration?

**Answer: mostly no.** One feature (`mom_12_1`, 12-1 month momentum) shows a
result that survives the overlap correction at the 1-day horizon and matches
a well-established academic effect. Nothing else does — including, notably,
`wr` and `rsi`, the two features the entire current dashboard is built on.

## Run

- Universe: current S&P 500 + Nasdaq-100, 514/518 tickers with enough history
- Period: 2021-08-17 to 2026-08-17 (5 years), 638,564 ticker-days
- 12 features × 6 targets (raw + market-adjusted forward return, 1/5/20-day)
  = 72 unconditional tests, plus 18 regime-conditional tests on the 3
  reversal features = **90 statistical tests total, no multiple-testing
  correction applied**. Treat every number below accordingly — at 90 tests,
  several |t| > 2 hits are the expected base rate under pure noise, not
  evidence.

Full numbers: `output/run.log`, `output/ic_summary.csv`, `output/ic_conditional.csv`.

## The current dashboard's own features (wr, rsi): no signal, any horizon

| feature | 1d t-stat | 5d t-stat (non-overlap) | 20d t-stat (non-overlap) |
|---|---|---|---|
| `wr`  | -0.54 | -1.41 | -0.62 |
| `rsi` | -0.07 |  0.51 |  0.94 |

None clear even the conventional |t| > 2 bar, let alone Harvey-Liu-Zhu's
suggested 3.0 for a new effect. This is the **third independent result**
pointing the same direction — after the two live diagnostics run earlier on
this exact oscillator design (gross 1-day edge of 1.6–3.8bps reversing to
-62 to -67bps at 20 days). I'd stop looking for a tradable edge in flat
Williams %R / RSI thresholds on this universe; three honest checks have now
failed to find one.

## The one credible result: 12-1 month momentum, 1-day horizon

`mom_12_1` = `log(P[t-21]/P[t-252])` — the classic Jegadeesh-Titman momentum
factor — is the top-ranked feature at **every** horizon by naive t-stat
(3.42 / 3.71 / 4.83 for 1/5/20 days). But the naive numbers overstate
significance for h > 1 because overlapping-window forward returns are
autocorrelated day to day — which is exactly what the non-overlapping
subsample check exists to catch:

| horizon | naive t-stat | non-overlap t-stat | non-overlap n |
|---|---|---|---|
| 1 day  | 3.42 | **3.42** (unchanged — no overlap at h=1) | 1001 |
| 5 day  | 3.71 | 1.69 | 200 |
| 20 day | 4.83 | 1.03 | 50 |

At 1-day horizon the non-overlap check doesn't touch the result (h=1 has no
overlap to correct), so **t=3.42 on 1001 independent days is the single
credible finding in this screen** — a real, well-documented academic effect
showing up where the literature would expect it. At 5- and 20-day horizons,
the apparent strength was mostly an artifact of counting overlapping windows
as independent observations.

`vol_20` (20-day realized volatility) shows a similar pattern — naive t=2.54
(5d) / 4.18 (20d), collapsing to 1.44 / 1.00 non-overlap. Worth a second look
with more data, not a candidate yet.

## Regime-conditional check: the Nagel hypothesis did not hold up

I specifically tested whether reversal signal (`wr`, `rsi`, `rev_5`)
concentrates in high-volatility / risk-off conditions, as the
liquidity-provision explanation for short-term reversal would predict. It
didn't — if anything the pattern ran the other way (e.g. `rsi` vs 20-day
market-adjusted return: t=3.69 in **low**-vol days, t=-0.86 in high-vol
days). Given this is 1 of 18 conditional tests with no overlap correction
applied to the conditional splits either, I'd treat this as noise, not as
evidence against the hypothesis — just as I'd treat it as noise if it *had*
come out the "right" way. The honest read is: this screen found no support
for reversal being conditional on volatility regime, in this simple form.

## Recommendation

Don't proceed with the full research pipeline for the WR/RSI mean-reversion
hypothesis — it has now failed three separate, independently-designed
checks. If there's appetite to keep pursuing predictive signals at all, the
one candidate worth the point-in-time-data investment is **12-1 month
momentum at short holding horizons**, not a grab-bag of everything in the
original feature list. Everything else here (trend, distance-from-MA,
liquidity, other return horizons) showed nothing distinguishable from noise
at any horizon once overlap is accounted for.

This conclusion should itself be held loosely: no multiple-testing
correction was applied across the 90 tests, the universe is
survivorship-biased, entries are approximated at close (not open), and
nothing here is cost-aware. A real go on momentum would still need
point-in-time membership data and a proper walk-forward/deflated-Sharpe
validation before being trusted — this screen only earns it the right to be
tested next, not the right to be believed yet.
