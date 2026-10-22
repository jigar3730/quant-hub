# Research log

Every signal evaluation, backtest, or rule variant tried — including the ones
that failed. Append-only. The number of entries is the multiple-testing count.

| Date | Hypothesis | Data (strategy, universe, dates, horizon) | Result (n runs / rows, spread, t) | Verdict | Next |
|---|---|---|---|---|---|
| 2026-10-22 | Launchpad tiers beat their own universe on forward returns | launchpad, all 4 cron universes + mega_runners, live scans 2026-09-06→10-16, h=5/10/20 | h20: Tier 3 +1.02% vs universe (57 runs, 1863 rows, t 4.1), Tier 2 +3.72% (21 runs, 26 rows), filtered −0.39%; Tier 1 never fired. Ordering monotone at all horizons | **Inconclusive** — only 15 dates / ~3 non-overlapping 20d windows, one regime, gross of costs. Live forward data, so no lookahead/survivorship | Let cron labels accumulate (fixed % bug); re-run monthly; need ≥ 30 independent weeks |
| 2026-10-22 | Dataset: research ETF history for the swing backtest | `quant-research warm-history` → `data/cache/prices/1d/research/` (27 tickers: 21 sector ETFs, SPY/RSP/QQQ/IWM, ^VIX/^TNX), Yahoo daily, split/dividend-adjusted, 2004-09-23→2026-10-21 | 0 missing, 0 NaN closes; SPY matches production cache exactly (last 30 bars). Young ETFs: XLC 2018, ARKF 2019, FDIG 2022, ARKG 2014, SCHD 2011, SCHG 2010 | Ready | ^VIX/^TNX include today's partial bar — drop bars ≥ decision date in the backtest. Universe membership is fixed (today's list), low but nonzero hindsight in ARK/FDIG additions |
| 2026-10-22 | Per-universe Launchpad edge (does the daily scan list need trimming?) | `universe_edge.sql`, h=10/20, live scans 09-06→10-16 | Independent weeks: **3** at h=10, **1** at h=20. h=10 spread: large +2.83, most_actives +0.77, mid +0.38, small +0.54 (was −0.65 counting overlapping runs) | **Inconclusive** — sign flips with sampling; no cut now | Pre-registered rule below. `mega_runners` is hindsight-selected (past winners): never use it as evidence of edge |

## Pre-registered decisions

Written before the data exists. Apply as written; changing a threshold after
seeing results invalidates the test.

**PR-1 — Launchpad daily universes (written 2026-10-22, due 2027-03-15 — 24 weeks of scans from 2026-09-07 + label lag).**
Run `universe_edge.sql` at h=10 and h=20. Remove a universe from the daily
cron if, at h=10, its mean spread is below its round-trip cost estimate
(large_cap_growth / mid_cap_growth 0.10%, most_actives 0.25%,
small_cap_growth 0.50%) **or** its `t_over_weeks` < 1, with at least 12
independent weeks. Fewer than 12 weeks → keep everything and extend the
deadline by one quarter. h=20 is reported but not part of the rule.

## Results after PR-1

| Date | Hypothesis | Data | Result | Verdict | Next |
|---|---|---|---|---|---|
| 2026-10-22 | Sector-ETF swing rules (production defaults, untuned) have edge after costs | `quant-research swing-backtest`, 21 sector ETFs, signals 2005-12→2026-10, next-open fills, 2 bps/side, max 3 concurrent | 341 trades, expectancy −0.05R (t −0.8), PF 0.92, CAGR −0.45%, MaxDD −26.7%, 15/21 losing years. SPY B&H 11.1% CAGR; SPY-with-regime-gate 4.9%; top-RS monthly 11.6% | **No edge** (sensitivity grid and skeptic review not run — result was far enough below zero that tuning would be curve-fitting) | Strategy retired 2026-10-22; code archived on `research/swing-backtest` and tag `archive/pre-launchpad-focus` |

**PR-2 — Launchpad rubric changes (written 2026-10-22, before any backfill result was viewed).**
Evidence base: Saturday point-in-time backfill scans (`metadata.data_provenance.backfill`),
universes large/mid/small_cap_growth + most_actives, labeled at h=10/20/63.
Design period: scan dates before 2025-01-01. Holdout: 2025-01-01 onward — not looked at
while choosing a change. Tooling: `quant-research launchpad-factors`.
A rubric change (factor weight, threshold, gate, or eligibility rule) is promoted only if, on
the **holdout** at h=20: (a) the new score's mean per-run rank IC is higher than the current
`final_score`'s, and (b) the new actionable set (Tier 1+2) beats its universe mean with
t ≥ 2 over non-overlapping runs, and (c) h=10 does not get worse. Changes are chosen on the
design period only; at most 3 candidate rubrics are taken to the holdout (each one counts as
a test here). Known bias, stated up front: universes are today's members (survivorship);
`most_actives` is today's screener, so its absolute returns are inflated — evaluate relative
to the same run's universe mean.

**PR-2 design-period results (2026-10-22, holdout not yet viewed).** Clean labels (`price_gap`
fix), 4 universes, 2022-05→2024-12, t over non-overlapping runs, returns clipped per run.
Rubric `final_score` IC ≈ 0 at h=10/20/63; no rubric factor |t| ≥ 2; Tier 2 underperforms its
universe (−11.2% at h=63, t −2.45). Benchmarks: 6-month momentum IC 0.13 (t 2.2) at h=63.
Candidates (defined before their design numbers were viewed; 3 tests counted):
C1 eligible ∩ top-20% 6m momentum: +1.47% h20 (t 2.07), +5.38% h63 (t 1.94);
C2 universe top-20% momentum: ~0; C3 C1 ∩ squeeze≥25: −8.3% h63 (t −2.9).
**Frozen for holdout: C1 only.**

**PR-2 holdout result (2026-10-22, viewed once, after freezing C1).** 2025-01→2026-09.
C1: −0.51% h10 (t −1.1), −0.88% h20 (t −1.0), −5.18% h63 (t −2.08) — sign flipped vs design.
`final_score` IC −0.02/−0.02/+0.07 (all |t| < 1.3). Eligible-but-below-Tier-2 (Tier 3)
underperforms its universe: −0.76% h20 (t −2.35), −5.95% h63 (t −2.83); filtered slightly
outperforms (t ≈ 2.1). **Verdict: no rubric change promoted. The Launchpad rubric has no
measurable predictive edge on 4.5 years of point-in-time scans (~900 runs, ~105k labeled
ticker-dates), and the one candidate that looked good in-sample failed out-of-sample.**
The 2022-26 holdout is now used; any new hypothesis must be pre-registered and judged on
live scans from 2026-10-23 onward. The earlier 6-week live result (first table row) was also
contaminated by sparse-history labels (fixed in e6f5473) and should not be cited.

**Project decision (2026-10-22, user).** No strategy showed out-of-sample edge; development
stopped. Summary and rationale: [CONCLUSION.md](CONCLUSION.md).
