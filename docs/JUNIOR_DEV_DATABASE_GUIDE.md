# Quant Hub Junior Developer Database Guide

**Scope:** Launchpad and Lynch only
**Last updated:** 2026-07-19

## Mental model

```text
Universe → Launchpad or Lynch CLI → scan_runs → ticker_results.detail
                                      └──────→ signal_outcomes (Launchpad ML)
```

Postgres is the system of record. A run is unique by `(scan_date, strategy_id, universe_id)`, so a same-day rerun replaces the existing snapshot.

Only these product strategy IDs are valid for current scan data:

| Strategy ID | Product | Actionable rows |
|---|---|---|
| `launchpad` | Quality technical scan | `tier IN ('Tier 1', 'Tier 2')` |
| `lynch` | Fundamental screen | `eligible IS TRUE` |

## Connect and inspect

```bash
docker exec -it quant-hub-db psql -U quant -d quant_hub
docker exec quant-hub quant-hub status
docker exec quant-hub quant-hub report --strategy launchpad --universe sp500_index
```

## Tables

### `scan_runs`

One row per product/universe/date. Important columns: `id`, `scan_date`, `scan_time`, `strategy_id`, `universe_id`, `universe_size`, tier counts, `actionable_count`, `regime_label`, `regime_multiplier`, and `metadata`.

Launchpad uses tier counts for Tier 1–3. Lynch uses them for category aggregates; consult `metadata.category_counts` for the explicit category map.

### `ticker_results`

One row per symbol per run. Its primary key is `(run_id, ticker)`.

| Column | Meaning |
|---|---|
| `eligible` | Passed the product gate |
| `tier` | Launchpad Tier 1/2/3/filtered or Lynch category/filtered |
| `final_score` | Launchpad technical score or Lynch percentage-of-checks score |
| `filter_reason` | Gate failure reason |
| `detail` | Complete JSONB ticker payload |

### ML tables

`signal_outcomes` stores forward-return labels keyed by `(run_id, ticker, horizon_days)`. `ml_models` registers Launchpad model artifacts, feature schema, dates, and metrics.

## Detail JSONB fields

```sql
-- Launchpad
tr.detail->'summary'->>'final_adjusted_score'
tr.detail->'scores'->'squeeze_intensity'->>'score'
tr.detail->'scores'->'volume_vacuum_depth'->>'score'
tr.detail->'eligibility'->>'fail_reason'

-- Lynch
tr.detail->>'lynch_score'
tr.detail->>'peg_ratio'
tr.detail->'categories'
tr.detail->'metrics'->>'institutional_ownership'
```

Cast JSON text before numeric comparisons, e.g. `(tr.detail->>'peg_ratio')::float`.

## Everyday queries

Latest run by product and universe:

```sql
SELECT strategy_id, universe_id, MAX(scan_date) AS latest_scan
FROM scan_runs
WHERE strategy_id IN ('launchpad', 'lynch')
GROUP BY strategy_id, universe_id
ORDER BY strategy_id, universe_id;
```

Latest Launchpad watchlist:

```sql
SELECT tr.ticker, tr.tier, tr.final_score
FROM ticker_results tr JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'launchpad' AND sr.universe_id = 'sp500_index'
  AND sr.scan_date = (SELECT MAX(scan_date) FROM scan_runs
                      WHERE strategy_id = 'launchpad' AND universe_id = 'sp500_index')
  AND tr.tier IN ('Tier 1', 'Tier 2')
ORDER BY tr.final_score DESC;
```

Latest Lynch candidates:

```sql
SELECT tr.ticker, tr.final_score, tr.detail->'categories' AS categories
FROM ticker_results tr JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'lynch' AND sr.universe_id = 'sp500_index'
  AND sr.scan_date = (SELECT MAX(scan_date) FROM scan_runs
                      WHERE strategy_id = 'lynch' AND universe_id = 'sp500_index')
  AND tr.eligible IS TRUE
ORDER BY tr.final_score DESC NULLS LAST;
```

For the primary combined query, use the Launchpad ∩ Lynch SQL in [Analytics Guide](ANALYTICS_GUIDE.md).

## Safe habits

- Query Postgres, not CSV exports, for full history and JSON detail.
- Filter `strategy_id` to `launchpad` or `lynch`.
- Treat missing Lynch scores as missing data, not zero.
- Use `run_id` to join labels to the exact historical signal.
- Do not truncate `scan_runs`; it cascades ticker rows and ML labels.

Schema source: `src/quant_hub/infrastructure/postgres/schema.sql`.
