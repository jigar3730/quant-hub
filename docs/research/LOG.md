# Research log

Every signal evaluation, backtest, or rule variant tried — including the ones
that failed. Append-only. The number of entries is the multiple-testing count.

| Date | Hypothesis | Data (strategy, universe, dates, horizon) | Result (n runs / rows, spread, t) | Verdict | Next |
|---|---|---|---|---|---|
| 2026-10-22 | Launchpad tiers beat their own universe on forward returns | launchpad, all 4 cron universes + mega_runners, live scans 2026-09-06→10-16, h=5/10/20 | h20: Tier 3 +1.02% vs universe (57 runs, 1863 rows, t 4.1), Tier 2 +3.72% (21 runs, 26 rows), filtered −0.39%; Tier 1 never fired. Ordering monotone at all horizons | **Inconclusive** — only 15 dates / ~3 non-overlapping 20d windows, one regime, gross of costs. Live forward data, so no lookahead/survivorship | Let cron labels accumulate (fixed % bug); re-run monthly; need ≥ 30 independent weeks |
