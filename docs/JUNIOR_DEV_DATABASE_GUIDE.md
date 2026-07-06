# Quant Hub — Junior Developer Database & Query Guide

**Version:** 1.0  
**Audience:** Junior developers joining the project  
**Last updated:** 2026-07-06

**Goal:** Understand where scan data lives, how tables relate, and run everyday SQL/CLI queries safely.

**Related:** [Data Model / ERD](DATA_MODEL.md) · [Analytics Guide](ANALYTICS_GUIDE.md) · [Run Team Quickstart](RUN_TEAM_QUICKSTART.md) · [User Manual](USER_MANUAL.md) · [Runbook](RUNBOOK.md)

---

## Table of contents

1. [Mental model](#1-mental-model-read-this-first)
2. [Application setup](#2-application-setup-where-things-live)
3. [Database schema](#3-database-schema)
4. [The detail JSONB column](#4-the-detail-jsonb-column-cheat-sheet)
5. [Day-to-day queries](#5-day-to-day-queries-copy-paste)
6. [CLI quick reference](#6-cli-quick-reference)
7. [Pitfalls](#7-pitfalls-avoid-these)
8. [Where to look in code](#8-where-to-look-in-code)
9. [Learning path](#9-suggested-learning-path-for-a-new-junior-dev)
10. [Further reading](#10-further-reading)

---

## 1. Mental model (read this first)

Quant Hub runs **scanners** on ticker universes and saves results to **PostgreSQL**. That DB is the **system of record** — the dashboard, digests, and most analytics read from it.

```text
Universe (ticker list)  →  Scanner CLI/cron  →  scan_runs (1 row per run)
                                              →  ticker_results (1 row per ticker per run)
                                              →  detail JSONB (full per-ticker report)
```

**One scan run** is uniquely identified by:

```text
(scan_date, strategy_id, universe_id)
```

If you rerun the same strategy/universe on the same day, Postgres **replaces** that run (upsert). There is no intraday history for the same day.

| Strategy | Cadence | What “actionable” means |
|----------|---------|-------------------------|
| `breakout` | Daily | `tier IN ('Tier 1', 'Tier 2')` |
| `swing` | Weekly | `tier IN ('SETUP_LONG', 'SETUP_SHORT')` |
| `lynch` | Fundamental (often weekly) | `eligible = true` / Lynch passed |
| `mean_reversion` | Daily | `tier = 'HIGH_CONVICTION'` |

---

## 2. Application setup (where things live)

### Docker stack

| Component | Container | Host access |
|-----------|-----------|-------------|
| App (dashboard + CLIs + cron) | `quant-hub` | Dashboard `http://<host>:5002` |
| Database | `quant-hub-db` | Postgres `localhost:5433` |

```bash
cd /opt/stacks/quant-hub
docker compose ps
docker exec quant-hub quant-hub status
```

### Connect to Postgres

**Interactive shell:**

```bash
docker exec -it quant-hub-db psql -U quant -d quant_hub
```

**Connection string** (host-side tools):

```text
postgresql://quant:<password>@localhost:5433/quant_hub
```

Default password is often `quant` unless `POSTGRES_PASSWORD` is set in `.env`. See `.env.example`.

### Apply / refresh schema

```bash
docker exec quant-hub quant-hub init-db
```

Schema source: `src/quant_hub/infrastructure/postgres/schema.sql`

### Data vs code paths

| What | Live path (production) |
|------|-------------------------|
| Postgres files | `/mnt/fast/quant-data/postgres/` |
| Scan CSV/JSON exports | `/mnt/fast/quant-data/data/output/` |
| Price cache | `/mnt/fast/quant-data/data/cache/` |
| Universe config | `/mnt/fast/quant-data/data/universes.json` |

**Rule:** Query **Postgres** for analytics. File exports can be stale or incomplete (e.g. swing setups CSV ≠ full universe in DB).

---

## 3. Database schema

### Entity relationship

```mermaid
erDiagram
    scan_runs ||--|{ ticker_results : "run_id"
    scan_runs ||--o{ signal_outcomes : "run_id"
    scan_runs {
        bigint id PK
        date scan_date
        varchar strategy_id
        varchar universe_id
        int actionable_count
        jsonb metadata
    }
    ticker_results {
        bigint run_id PK_FK
        varchar ticker PK
        varchar tier
        float final_score
        jsonb detail
    }
    job_runs {
        bigint id PK
        varchar job_name
        varchar status
    }
```

`job_runs` is **audit only** — it tracks CLI job success/failure; it does not join to `scan_runs` by FK.

### Table: `scan_runs`

**One row per scan.** Summary + regime + counts.

| Column | Meaning |
|--------|---------|
| `id` | Surrogate PK; use as `run_id` in `ticker_results` |
| `scan_date` | Calendar date of the scan |
| `scan_time` | UTC timestamp when persisted |
| `strategy_id` | `breakout`, `swing`, `lynch`, `mean_reversion` |
| `universe_id` | e.g. `sp500_index`, `nasdaq100` |
| `universe_size` | Number of tickers scanned |
| `tier1_count`, `tier2_count`, `tier3_count` | Strategy-specific (see [DATA_MODEL.md](DATA_MODEL.md)) |
| `filtered_count` | Rejected / no setup / failed screen |
| `actionable_count` | Actionable names count |
| `regime_label` | e.g. `strong`, `neutral`, `weak` |
| `regime_multiplier` | Breakout score discount (0.6–1.0) |
| `metadata` | JSONB: regime detail, filter breakdown, Lynch preset, etc. |

**Useful metadata paths:**

```sql
metadata->'market_regime'->>'label'
metadata->'filter_breakdown'          -- {fail_reason: count}
metadata->'category_counts'           -- Lynch only
```

### Table: `ticker_results`

**One row per ticker per scan.** This is where most analyst queries start.

| Column | Meaning |
|--------|---------|
| `run_id` | FK → `scan_runs.id` |
| `ticker` | Symbol (uppercase) |
| `eligible` | Passed hard gate / Lynch screen |
| `tier` | Strategy tier (see below) |
| `sector_etf` | RS benchmark (breakout) |
| `final_score` | Primary sort score (denormalized) |
| `filter_reason` | Why excluded (when not eligible) |
| `detail` | **Full JSON report** — richest source |

**Tier values by strategy:**

| Strategy | Example `tier` values |
|----------|------------------------|
| breakout | `Tier 1`, `Tier 2`, `Tier 3`, `filtered` |
| swing | `SETUP_LONG`, `SETUP_SHORT`, `filtered` |
| lynch | `fast_grower`, `stalwart`, `asset_play`, `passed`, `filtered` |
| mean_reversion | `HIGH_CONVICTION`, `WATCHLIST`, `filtered` |

**Important:** The dashboard and deep analysis use `detail` JSONB. Indexed columns are shortcuts; use `detail` when you need factor scores, Lynch institutional %, swing quality, etc.

### Table: `job_runs`

Cron/CLI audit log — “did the job finish?”

```sql
SELECT job_name, status, started_at, tickers_fetched, tickers_failed, error_message
FROM job_runs
ORDER BY started_at DESC
LIMIT 10;
```

### Table: `signal_outcomes` (ML)

Forward returns after a signal. Populated by `quant-ml label`. Join on `(run_id, ticker)`.

| Column | Meaning |
|--------|---------|
| `horizon_days` | 5, 10, 20, 63 |
| `forward_return_pct` | Stock return after signal |
| `excess_return_pct` | vs SPY |
| `label_status` | `ok`, `pending`, `no_price`, etc. |

See [ML_FOUNDATION.md](ML_FOUNDATION.md) if you work on labels/training.

### Table: `ml_models` (ML)

Registry of trained models (artifact path, metrics, feature schema). See [ML_OPS.md](ML_OPS.md).

### Indexes

| Index | Table | Column(s) |
|-------|-------|-----------|
| PK | `scan_runs` | `(scan_date, strategy_id, universe_id)` UNIQUE |
| PK | `ticker_results` | `(run_id, ticker)` |
| `idx_scan_runs_date` | `scan_runs` | `scan_date DESC` |
| `idx_ticker_results_ticker` | `ticker_results` | `ticker` |
| `idx_job_runs_started` | `job_runs` | `started_at DESC` |

---

## 4. The `detail` JSONB column (cheat sheet)

Always join `ticker_results tr` → `scan_runs sr ON sr.id = tr.run_id`.

### Breakout

```sql
tr.detail->'summary'->>'final_adjusted_score'
tr.detail->'summary'->>'normalized_score'
tr.detail->'scores'->'compression'->>'score'
tr.detail->'scores'->'rs_market'->>'score'
tr.detail->>'tier_reason'
```

### Swing

```sql
tr.detail->'setup_detail'->>'swing_score'
tr.detail->'setup_detail'->>'quality_label'   -- A/B/C/D
tr.detail->'setup_detail'->>'rsi'
```

### Lynch

```sql
tr.detail->>'lynch_score'
tr.detail->>'institutional_pct'
tr.detail->>'analyst_count'
tr.detail->>'peg_ratio'
tr.detail->'categories'                        -- JSON array
tr.detail->'metrics'->>'institutional_ownership'
```

### Mean reversion

```sql
tr.detail->'summary'->>'mean_reversion_score'
tr.detail->'setup_detail'->'trade_plan'->>'entry_trigger'
tr.detail->'setup_detail'->'trade_plan'->>'stop_loss'
```

Cast floats when aggregating:

```sql
(tr.detail->'scores'->'compression'->>'score')::float
```

---

## 5. Day-to-day queries (copy-paste)

Replace `sp500_index` and dates as needed. Exclude test data in production views:

```sql
AND sr.universe_id NOT IN ('test-upsert', 'custom')
AND sr.scan_date <= CURRENT_DATE
```

### 5.1 Is the DB healthy?

```sql
SELECT 'scan_runs' AS tbl, COUNT(*) FROM scan_runs
UNION ALL SELECT 'ticker_results', COUNT(*) FROM ticker_results
UNION ALL SELECT 'job_runs', COUNT(*) FROM job_runs;
```

Or: `docker exec quant-hub quant-hub status`

### 5.2 Latest scan per strategy

```sql
SELECT strategy_id, universe_id, MAX(scan_date) AS latest
FROM scan_runs
WHERE scan_date <= CURRENT_DATE
GROUP BY strategy_id, universe_id
ORDER BY strategy_id, universe_id;
```

### 5.3 Latest breakout actionable list

```sql
SELECT tr.ticker, tr.tier, tr.final_score,
       tr.detail->'summary'->>'normalized_score' AS norm
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'breakout'
  AND sr.universe_id = 'sp500_index'
  AND sr.scan_date = (
    SELECT MAX(scan_date) FROM scan_runs
    WHERE strategy_id = 'breakout' AND universe_id = 'sp500_index'
  )
  AND tr.tier IN ('Tier 1', 'Tier 2')
ORDER BY tr.final_score DESC;
```

### 5.4 Ticker history across all scans (actionable only)

```sql
SELECT sr.scan_date, sr.strategy_id, sr.universe_id,
       tr.tier, tr.final_score,
       tr.detail->>'institutional_pct' AS inst_pct
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE tr.ticker = 'NVDA'
  AND sr.scan_date <= CURRENT_DATE
  AND (
    (sr.strategy_id = 'breakout' AND tr.tier IN ('Tier 1', 'Tier 2'))
    OR (sr.strategy_id = 'swing' AND tr.tier IN ('SETUP_LONG', 'SETUP_SHORT'))
    OR (sr.strategy_id = 'mean_reversion' AND tr.tier = 'HIGH_CONVICTION')
    OR (sr.strategy_id = 'lynch' AND tr.eligible IS TRUE AND tr.tier != 'filtered')
  )
ORDER BY sr.scan_date DESC
LIMIT 50;
```

**CLI equivalent:**

```bash
docker exec quant-hub quant-hub ticker history NVDA --json
docker exec quant-hub quant-hub ticker show NVDA --strategy lynch --universe sp500_index --date 2024-06-07 --json
```

### 5.5 Persistence — actionable 3+ days this week

```sql
SELECT tr.ticker,
       COUNT(*) AS days_actionable,
       ROUND(AVG(tr.final_score)::numeric, 1) AS avg_score
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'breakout'
  AND sr.universe_id = 'sp500_index'
  AND sr.scan_date >= CURRENT_DATE - INTERVAL '7 days'
  AND tr.tier IN ('Tier 1', 'Tier 2')
GROUP BY tr.ticker
HAVING COUNT(*) >= 3
ORDER BY days_actionable DESC;
```

### 5.6 Cross-strategy convergence

See full query in [ANALYTICS_GUIDE.md §5.4](ANALYTICS_GUIDE.md). Adjust dates — breakout is daily, swing weekly, Lynch often Saturday.

### 5.7 Why was a ticker filtered?

```sql
SELECT tr.ticker, tr.tier, tr.filter_reason,
       tr.detail->'eligibility'->>'fail_reason' AS detail_reason
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'breakout'
  AND sr.universe_id = 'sp500_index'
  AND sr.scan_date = '2024-06-07'
  AND tr.ticker = 'XYZ';
```

### 5.8 Scan-level rejection breakdown

```sql
SELECT sr.scan_date,
       sr.metadata->'filter_breakdown' AS rejections,
       sr.actionable_count
FROM scan_runs sr
WHERE sr.strategy_id = 'breakout'
  AND sr.universe_id = 'sp500_index'
ORDER BY sr.scan_date DESC
LIMIT 10;
```

### 5.9 Join signals to forward returns (ML)

```sql
SELECT sr.scan_date, tr.ticker, tr.tier,
       so.horizon_days, so.forward_return_pct, so.excess_return_pct
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
JOIN signal_outcomes so ON so.run_id = tr.run_id AND so.ticker = tr.ticker
WHERE sr.strategy_id = 'breakout'
  AND tr.tier IN ('Tier 1', 'Tier 2')
  AND so.label_status = 'ok'
  AND so.horizon_days = 10
ORDER BY sr.scan_date DESC
LIMIT 100;
```

More SQL recipes: [ANALYTICS_GUIDE.md](ANALYTICS_GUIDE.md) §5.

---

## 6. CLI quick reference

Run inside container: `docker exec quant-hub <command>`

| Task | Command |
|------|---------|
| DB + recent scans | `quant-hub status` |
| Latest scan summary JSON | `quant-hub report --strategy breakout --universe sp500_index` |
| Ticker actionable history | `quant-hub ticker history NVDA [--json\|--csv out.csv]` |
| One ticker snapshot | `quant-hub ticker show NVDA --strategy lynch --universe sp500_index --date 2024-06-07` |
| ML label counts | `quant-ml status` |
| Run a scan manually | `quant-scan --universe sp500_index --cache` |

Repository code: `src/quant_hub/infrastructure/postgres/repository.py`

---

## 7. Pitfalls (avoid these)

| Pitfall | What to do instead |
|---------|-------------------|
| Querying CSV exports for swing full universe | Use Postgres — CSV is setups-only |
| Expecting multiple runs per day | Same day rerun **overwrites**; only latest kept |
| Including test data | Filter out `test-upsert`, `custom`, and dates `> CURRENT_DATE` |
| Breakout vs swing date alignment | Swing runs weekly; don't assume same `scan_date` across strategies |
| Trusting `final_score` alone for Lynch | Check `detail->>'lynch_score'` and `eligible`; null score ≠ zero |
| Selecting full `detail` on huge result sets | Select specific JSON paths |
| Editing repo `data/` on prod | Edit `/mnt/fast/quant-data/data/` or copy after change |

Fixture universe IDs are defined in `src/quant_hub/infrastructure/postgres/fixtures.py`.

---

## 8. Where to look in code

| Question | File |
|----------|------|
| Schema DDL | `src/quant_hub/infrastructure/postgres/schema.sql` |
| Upsert / load_report / ticker_history | `src/quant_hub/infrastructure/postgres/repository.py` |
| Actionable rules | `src/quant_hub/history/actionable.py` |
| History column projection | `src/quant_hub/history/ticker_projection.py` |
| Breakout report shape | `src/quant_hub/report/builder.py` |
| Lynch metrics (institutional %) | `src/quant_hub/lynch/runner.py`, `lynch/metrics.py` |
| Dashboard reads DB | `src/quant_hub/dashboard/app.py` |
| Fixture universe list | `src/quant_hub/infrastructure/postgres/fixtures.py` |

---

## 9. Suggested learning path for a new junior dev

1. Run `quant-hub status` and connect with `psql`.
2. Run query **5.2** (latest scans) and **5.3** (latest actionable).
3. Pick one ticker; run `quant-hub ticker history SYMBOL --json`.
4. Inspect one row: `SELECT detail FROM ticker_results WHERE run_id = ? AND ticker = ?` (format with `\x` or export JSON).
5. Read [ANALYTICS_GUIDE.md](ANALYTICS_GUIDE.md) §5 for analyst workflows.
6. Read [DATA_MODEL.md](DATA_MODEL.md) §9 for full `detail` schemas per strategy.

---

## 10. Further reading

| Doc | When to use |
|-----|-------------|
| [DATA_MODEL.md](DATA_MODEL.md) | Full ERD, metadata fields, retention |
| [ANALYTICS_GUIDE.md](ANALYTICS_GUIDE.md) | Production SQL cookbook |
| [USER_MANUAL.md](USER_MANUAL.md) | Dashboard + ticker history UI |
| [RUN_TEAM_QUICKSTART.md](RUN_TEAM_QUICKSTART.md) | Docker ops, backups, cron |
| [ML_FOUNDATION.md](ML_FOUNDATION.md) | `signal_outcomes` and training |
