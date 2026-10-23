# Project conclusion (2026-10-22): no edge found — development stopped

**Bottom line:** none of the strategies in quant-hub showed a measurable, out-of-sample edge.
Development stops here. The code, Postgres history, and price caches are kept so the work can
be audited or resumed; nothing in this repo should be used to make trading decisions.
Full evidence and every test (failures included) are in [LOG.md](LOG.md).
Lessons and a starter kit for the next project: [../RETROSPECTIVE.md](../RETROSPECTIVE.md).

## What was tested

| Strategy | Test | Result | Verdict |
|---|---|---|---|
| Sector-ETF swing | 20-year backtest, 21 sector ETFs, next-open fills, 2 bps/side | 341 trades, CAGR −0.45% (SPY buy-and-hold 11.1%), expectancy −0.05R, 15/21 losing years | **No edge** — deleted (tag `archive/pre-launchpad-focus`) |
| Launchpad rubric | Point-in-time weekly backfill 2022-05 → 2026-09, 4 universes, ~900 runs, ~105k labeled ticker-dates, h=10/20/63; design < 2025-01-01, holdout after (rule pre-registered as PR-2) | `final_score` rank IC ≈ 0 at every horizon; no component (squeeze, tightness, volume, trend, MACD) reaches \|t\| ≥ 2; Tier 2/3 *underperform* their own universe (holdout Tier 3: −5.95% at h63, t −2.83); Tier 1 essentially never fires | **No edge** |
| Launchpad + momentum (C1) | Best of 3 candidates frozen on design period, judged once on holdout | Design +5.38% h63 (t 1.94) → holdout −5.18% h63 (t −2.08) | **Failed out-of-sample** |
| Lynch fundamental screen | Not testable: fundamentals are not point-in-time | — | Switched off, never validated |

Known biases, all of which would flatter results — and results were still flat or negative:
universes are today's members (survivorship), Yahoo-only daily bars, no transaction costs in
the Launchpad tests.

## Why not continue

- The 2022-26 data is spent as a holdout; tuning more variants on it would be curve-fitting.
- Daily-bar chart patterns on liquid US stocks are crowded; this project found no evidence
  against that prior.
- The only credible next steps are a different hypothesis (e.g. documented momentum /
  trend premia) on survivorship-free paid data (Norgate, ~$300–600/yr) with a cost-aware
  backtest. Realistic upside even then is a few %/yr over the index with long drawdowns.
  Judged not worth the money and time; an index fund is the baseline this would have to beat.

## If anyone resumes

1. Write the hypothesis and pass rule into LOG.md *before* looking at data.
2. Use survivorship-free history and include costs.
3. Use `quant-research launchpad-factors` / the `signal-eval` skill for measurement, and the
   `quant-skeptic` agent before believing any result.
4. All cron jobs are commented out in `docker/crontab` (2026-10-22). To get untouched
   out-of-sample data for the Launchpad rubric, re-enable the daily scans and Saturday labels.
