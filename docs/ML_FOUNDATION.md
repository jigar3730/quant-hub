# ML Foundation (Phase 1)

**Status:** Phase 1 — labels + feature export (no training models yet)  
**Audience:** Operators and anyone building Phase 2 models  
**Related:** [Data Model](DATA_MODEL.md) · [Runbook](RUNBOOK.md) · [Analytics Guide](ANALYTICS_GUIDE.md)

---

## ML phase scope (current)

Until swing ML and historical backfill are solid, the platform runs in **narrow scope**:

| Active | Paused |
|--------|--------|
| `quant-swing --universe sp500` (Fri 5:45 PM ET cron) | Breakout, Lynch, other universes |
| `quant-ml label --strategy swing --universe sp500` (Sat 6 AM ET) | Daily/weekly digests, `quant-swing-all`, `quant-scan-all` |

**Manual one-shot** (scan + label):

```bash
docker exec quant-hub bash /app/scripts/ml-phase-swing-sp500.sh
```

**Operator commands** (scoped):

```bash
docker exec quant-hub quant-swing --universe sp500 --no-email
docker exec quant-hub quant-ml label --strategy swing --universe sp500 --since 2026-01-01
docker exec quant-hub quant-ml export-features --strategy swing --universe sp500
```

**Backfill** — historical swing sp500 scans for ML training:

```bash
# 1. Backfill weekly swing signals (point-in-time from 10y weekly parquet)
docker exec quant-hub quant-backfill swing --universe sp500 --since 2024-01-01

# 2. Warm extended daily cache (~5y) for forward-return labels
docker exec quant-hub quant-ml warm-cache --universe sp500

# 3. Label all backfilled runs
docker exec quant-hub quant-ml label --strategy swing --universe sp500 --since 2024-01-01

# 4. Export training features
docker exec quant-hub quant-ml export-features --strategy swing --universe sp500 --since 2024-01-01
```

`quant-backfill swing` truncates weekly OHLCV to each Friday, skips staleness checks, and sets `metadata.data_provenance.backfill=true`. Re-run with `--no-resume` to overwrite dates.

Do not run `full-rescan.sh` or `TRUNCATE scan_runs` during this phase.

To restore full multi-strategy cron after ML phase, uncomment the disabled block in `docker/crontab` and rebuild the container.

---

## Purpose

Phase 1 establishes the **data layer** required for robust ML ops:

1. **Labels** — forward returns stored in Postgres (`signal_outcomes`)
2. **Features** — flattened scan snapshots exported to Parquet (`data/ml/features/`)
3. **Governance** — leakage rules, schema versioning, retention policy

No model training or inference runs in Phase 1. The goal is to answer:

> For every signal on date *D*, what was the forward return over 5/10/20/63 trading days?

---

## Architecture

```text
scan_runs + ticker_results (signals)
        │
        ├─► quant-ml label ──► signal_outcomes (Postgres)
        │
        └─► quant-ml export-features ──► data/ml/features/*.parquet
```

| Layer | Storage | CLI |
|-------|---------|-----|
| Signals | `scan_runs`, `ticker_results` | existing scanners |
| Labels | `signal_outcomes` | `quant-ml label` |
| Features | `data/ml/features/` | `quant-ml export-features` |

---

## Schema: `signal_outcomes`

Primary key: `(run_id, ticker, horizon_days)`

| Column | Description |
|--------|-------------|
| `anchor_date` | Last price date used by the scan (`metadata.data_provenance.as_of_price`, else `scan_date`) |
| `horizon_days` | Forward window in **trading sessions** (default: 5, 10, 20, 63) |
| `forward_return_pct` | Close-to-close return from first close after anchor |
| `forward_max_gain_pct` | Peak gain along the path |
| `forward_max_drawdown_pct` | Worst drawdown along the path |
| `spy_forward_return_pct` | SPY return over same window |
| `excess_return_pct` | Stock return minus SPY return |
| `label_binary` | `forward_return_pct >= 2.0` (configurable) |
| `label_status` | `ok`, `no_price`, `invalid_anchor`, `insufficient_future_bars` |
| `computed_at` | When the label job last wrote this row |

Labels are **recomputable**: re-run `quant-ml label` after more price history accumulates; rows upsert in place.

---

## Label definitions (no lookahead)

1. **Anchor** — `as_of_price` from scan provenance, or `scan_date` if missing.
2. **Entry** — first daily close on a trading day **strictly after** `anchor_date`.
3. **Exit** — close on the *N*th trading session after entry (`horizon_days`).
4. **Path metrics** — max gain and max drawdown computed on closes between entry and exit.
5. **Benchmark** — SPY from the same daily parquet cache (`data/cache/prices/1d/2y/SPY.parquet`).

Prices come only from the **daily cache**. If a ticker has no cache file, `label_status = no_price`.

---

## Feature export

`quant-ml export-features` flattens `ticker_results.detail` plus run context into tabular columns.

- **Schema version:** `v1` (`FEATURE_SCHEMA_VERSION` in config)
- **Output:** `data/ml/features/{strategy}/{universe}/features_*.parquet`
- **Optional labels:** joined from `signal_outcomes` for a chosen `--horizon` (default 10)

Strategy-specific columns:

| Strategy | Key columns |
|----------|-------------|
| breakout | 9 factor scores, `normalized_score`, `tier`, `sector_etf` |
| swing | `swing_score`, `quality_label`, RSI, EMAs, ATR |
| lynch | `lynch_score`, PEG, P/E, categories, fetch quality flags |

Bump `FEATURE_SCHEMA_VERSION` when adding or renaming exported columns.

---

## CLI reference

Run inside the container:

```bash
docker exec quant-hub quant-ml status
docker exec quant-hub quant-ml label --strategy breakout --universe sp500 --since 2026-01-01
docker exec quant-hub quant-ml label --run-id 123
docker exec quant-hub quant-ml export-features --strategy breakout --universe sp500 --since 2026-01-01
docker exec quant-hub quant-ml export-features --per-run --no-labels
```

Apply schema after upgrade:

```bash
docker exec quant-hub quant-hub init-db
```

---

## Schedule

- **Saturday 6:00 AM ET** — `quant-ml label --since <90 days ago>` (cron)
- **Weekly full coverage** — also runs label step at the end of `weekly-full-coverage.sh`

Re-run labeling manually after bulk historical imports.

---

## Leakage rules (non-negotiable)

1. **Features** — only fields present in `detail` at scan time; never join future scans.
2. **Labels** — only prices **after** `anchor_date`; never use same-day close as entry.
3. **Walk-forward eval** (Phase 2) — train on `scan_date < T`, test on `scan_date >= T`; no random date shuffles.
4. **Lynch partial fetches** — exclude rows with `fetch_complete = false` or `fetch_error = true` from training sets.
5. **Same-day rescan** — Postgres upsert replaces one run per `(scan_date, strategy, universe)`; use `run_id` for lineage.

---

## Retention policy

| Action | ML impact |
|--------|-----------|
| Normal daily/weekly scans | Safe — history accumulates |
| `full-rescan.sh` / `TRUNCATE scan_runs` | **Destroys training data** — avoid on production |
| Fixture cleanup (`quant-hub cleanup-fixtures`) | Removes test universes only |
| Parquet cache eviction | Labels become `no_price` until cache refilled |

**Policy:** Do not truncate `scan_runs` on the production database. Archive old runs to cold storage if disk is a concern; Phase 2 may add an explicit archive script.

`signal_outcomes` rows cascade-delete when a parent `scan_runs` row is deleted.

---

## Exit criteria (Phase 1)

- [ ] `signal_outcomes` populated for recent scan history
- [ ] SQL query: Tier 1 breakout on date D → 10d forward return
- [ ] Parquet export with `feature_schema_version = v1`
- [ ] Unit tests pass for label math and feature flattening

**Phase 2** (not in scope yet): `quant-ml train`, `quant-ml evaluate`, `ml_models` registry, LightGBM reranker.

---

## Example SQL

```sql
-- 10-day forward return for sp500 breakout Tier 1 signals
SELECT sr.scan_date, tr.ticker, tr.tier, so.forward_return_pct, so.label_binary
FROM scan_runs sr
JOIN ticker_results tr ON tr.run_id = sr.id
JOIN signal_outcomes so ON so.run_id = sr.id AND so.ticker = tr.ticker
WHERE sr.strategy_id = 'breakout'
  AND sr.universe_id = 'sp500'
  AND tr.tier = 'Tier 1'
  AND so.horizon_days = 10
  AND so.label_status = 'ok'
ORDER BY sr.scan_date DESC, so.forward_return_pct DESC;
```
