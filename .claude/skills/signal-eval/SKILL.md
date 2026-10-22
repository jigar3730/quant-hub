---
name: signal-eval
description: Measure whether a quant-hub scanner signal (Launchpad/Lynch tiers, a score threshold, a sector-swing rule) actually predicts forward returns, using labeled outcomes in Postgres. Use whenever asked "does this work", "is there edge/alpha", before changing a rule or threshold, or before building anything (UI, positions, digest) on top of a signal.
---

# Signal evaluation

Evidence first, opinions after. Every claim of edge must come from this
procedure and then go through the `quant-skeptic` agent before it is reported
as anything stronger than "inconclusive".

## 1. Make sure labels exist

Forward returns live in `signal_outcomes` (`label_status = 'ok'` means usable),
produced by `quant-ml label` (Saturday cron; horizons 5/10/20/63 trading days).

```bash
docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' quant-hub-db-dev \
  psql -U quant -d quant_hub -c "select horizon_days, label_status, count(*) from signal_outcomes group by 1,2 order by 1,2"
```

Missing labels → `docker exec quant-hub-dev quant-ml label --strategy <s> --since <date> --horizons 5,10,20`
(writes to the DB; it is what the cron does, so it's fine in dev).

## 2. Tier edge vs universe

```bash
docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' quant-hub-db-dev \
  psql -U quant -d quant_hub -v strategy=launchpad -v horizon=20 \
  < .claude/skills/signal-eval/tier_edge.sql
```

Read it as: `mean_spread_pct` = how much a tier beat its own universe on the
same date; `t_over_runs` uses runs (date × universe) as the unit. The universe
baseline strips out beta and "growth stocks went up this month".

## 2b. Per-universe edge over independent weeks

```bash
docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' quant-hub-db-dev \
  psql -U quant -d quant_hub -v strategy=launchpad -v horizon=10 \
  < .claude/skills/signal-eval/universe_edge.sql
```

One observation per non-overlapping window (every ceil(h/5)-th week), so
`indep_weeks` is the honest sample size. This is the query behind the
pre-registered universe-trim decision in `docs/research/LOG.md` (due
2027-03-15) — apply that rule as written; don't adjust thresholds after seeing
the numbers.

## 3. Interpret honestly

- Overlapping horizons: runs a few days apart with a 20-day horizon share most
  of their return window — distinct *weeks* is closer to the true sample size.
- < 30 distinct dates or < 100 signals: report **inconclusive**, regardless of
  how good the mean looks. Say how long until the sample is adequate.
- Report the gross spread; then subtract a realistic round trip (≥ 10 bps for
  liquid large caps, 30–100 bps for small caps) before calling it alpha.
- Break down by `universe_id` and by month; one hot universe or month driving
  the average is a regime bet, not an edge.

## 4. Record it

Append one entry to `docs/research/LOG.md` for every evaluation — including
failures and variants you discarded. The count of things tried is what makes
the multiple-testing check in `quant-skeptic` possible.

## Changing rules

Scoring/rubric paths are protected (see CLAUDE.md). To test a variant, compute
it in a research script or SQL against stored `detail` JSONB / price cache —
never by editing production scoring. Promote a variant only with user sign-off
after it passes out-of-sample.
