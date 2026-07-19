# Quant Hub Analytics Guide

**Scope:** Launchpad technical persistence, Lynch fundamentals, and Launchpad ∩ Lynch overlap
**Last updated:** 2026-07-19

Postgres is the analysis source of truth. Each product run is unique by `(scan_date, strategy_id, universe_id)`; a same-day rerun replaces it.

Connect with:

```bash
docker exec -it quant-hub-db psql -U quant -d quant_hub
```

## What accumulates

| Cadence | Data |
|---|---|
| Mon–Fri | Launchpad `sp500_index` run, then daily digest |
| Saturday 1:30 AM | Launchpad across stock universes |
| Saturday 5:00 AM | Lynch across stock universes |
| Saturday 7:50 AM | Weekly analytics payload for the digest |

`scan_runs` holds aggregates and `ticker_results` holds one full JSONB result per ticker. Use `signal_outcomes` only for Launchpad ML label analysis.

Actionable definitions:

```text
Launchpad: tier IN ('Tier 1', 'Tier 2')
Lynch:     eligible = true
```

## Primary combined analysis: Launchpad ∩ Lynch

The weekly combined signal is a ticker actionable in both the latest Launchpad and latest Lynch runs for the same universe. This query deliberately allows the technical and fundamental scans to have different dates.

```sql
WITH latest AS (
  SELECT strategy_id, universe_id, MAX(scan_date) AS scan_date
  FROM scan_runs
  WHERE strategy_id IN ('launchpad', 'lynch')
    AND universe_id = 'sp500_index'
  GROUP BY strategy_id, universe_id
),
launchpad AS (
  SELECT tr.ticker, sr.scan_date, tr.tier, tr.final_score
  FROM ticker_results tr
  JOIN scan_runs sr ON sr.id = tr.run_id
  JOIN latest l ON l.strategy_id = sr.strategy_id
             AND l.universe_id = sr.universe_id
             AND l.scan_date = sr.scan_date
  WHERE sr.strategy_id = 'launchpad'
    AND tr.tier IN ('Tier 1', 'Tier 2')
),
lynch AS (
  SELECT tr.ticker, sr.scan_date, tr.tier, tr.final_score,
         tr.detail->'categories' AS categories
  FROM ticker_results tr
  JOIN scan_runs sr ON sr.id = tr.run_id
  JOIN latest l ON l.strategy_id = sr.strategy_id
             AND l.universe_id = sr.universe_id
             AND l.scan_date = sr.scan_date
  WHERE sr.strategy_id = 'lynch' AND tr.eligible IS TRUE
)
SELECT l.ticker,
       l.scan_date AS launchpad_date, l.tier AS launchpad_tier,
       l.final_score AS launchpad_score,
       y.scan_date AS lynch_date, y.tier AS lynch_tier,
       y.final_score AS lynch_score, y.categories
FROM launchpad l
JOIN lynch y USING (ticker)
ORDER BY l.final_score DESC, y.final_score DESC;
```

The dashboard uses payload keys `overlap_count` and `launchpad_lynch_overlap`; do not query or describe a convergence count.

## Launchpad persistence

Persistence separates recurring quality setups from one-day appearances:

```sql
SELECT tr.ticker,
       COUNT(*) AS days_actionable,
       ROUND(AVG(tr.final_score)::numeric, 1) AS average_score,
       MAX(sr.scan_date) AS last_seen
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'launchpad'
  AND sr.universe_id = 'sp500_index'
  AND sr.scan_date >= CURRENT_DATE - INTERVAL '7 days'
  AND tr.tier IN ('Tier 1', 'Tier 2')
GROUP BY tr.ticker
HAVING COUNT(*) >= 3
ORDER BY days_actionable DESC, average_score DESC;
```

For changes between the two latest Launchpad runs:

```sql
WITH ranked AS (
  SELECT sr.scan_date, tr.ticker,
         DENSE_RANK() OVER (ORDER BY sr.scan_date DESC) AS date_rank
  FROM ticker_results tr JOIN scan_runs sr ON sr.id = tr.run_id
  WHERE sr.strategy_id = 'launchpad' AND sr.universe_id = 'sp500_index'
    AND tr.tier IN ('Tier 1', 'Tier 2')
),
today AS (SELECT ticker FROM ranked WHERE date_rank = 1),
prior AS (SELECT ticker FROM ranked WHERE date_rank = 2)
SELECT 'new' AS change, ticker FROM today WHERE ticker NOT IN (SELECT ticker FROM prior)
UNION ALL
SELECT 'dropped', ticker FROM prior WHERE ticker NOT IN (SELECT ticker FROM today);
```

## Lynch analytics

```sql
SELECT tr.ticker, tr.final_score AS lynch_score,
       tr.detail->'categories' AS categories,
       (tr.detail->>'pe_ratio')::float AS pe_ratio,
       (tr.detail->>'peg_ratio')::float AS peg_ratio
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'lynch' AND sr.universe_id = 'sp500_index'
  AND sr.scan_date = (
    SELECT MAX(scan_date) FROM scan_runs
    WHERE strategy_id = 'lynch' AND universe_id = 'sp500_index'
  )
  AND tr.eligible IS TRUE
ORDER BY tr.final_score DESC NULLS LAST;
```

Track score and category changes as fundamental snapshots, not as real-time financial statements:

```sql
SELECT sr.scan_date, tr.final_score AS lynch_score,
       tr.eligible AS passed, tr.detail->'categories' AS categories
FROM ticker_results tr JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'lynch' AND tr.ticker = 'NVDA'
ORDER BY sr.scan_date DESC;
```

## Launchpad ML outcomes

Use only completed labels and a chosen horizon:

```sql
SELECT sr.scan_date, tr.ticker, tr.tier, tr.final_score,
       so.forward_return_pct, so.excess_return_pct, so.label_binary
FROM scan_runs sr
JOIN ticker_results tr ON tr.run_id = sr.id
JOIN signal_outcomes so ON so.run_id = tr.run_id AND so.ticker = tr.ticker
WHERE sr.strategy_id = 'launchpad'
  AND tr.tier IN ('Tier 1', 'Tier 2')
  AND so.horizon_days = 20
  AND so.label_status = 'ok'
ORDER BY sr.scan_date DESC, tr.final_score DESC;
```

See [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) for label definitions, leakage controls, and evaluation.
