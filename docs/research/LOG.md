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
