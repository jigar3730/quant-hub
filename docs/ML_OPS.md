# ML Ops Guide

**Audience:** Operators running the ML data pipeline on the homelab stack  
**Status:** Phase 2 — labels, backfill, feature export, model training & evaluation  
**Related:** [ML Foundation](ML_FOUNDATION.md) (schema & leakage rules) · [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) · [Data Model](DATA_MODEL.md) · [Runbook](RUNBOOK.md) · [Swing Scanner](SWING_SCANNER.md) · [Launchpad Scanner](LAUNCHPAD_SCANNER.md)

---

## 1. What ML Ops does today

Quant Hub ML Ops prepares **training-ready datasets** from scan history for **swing** and **launchpad** (breakout/lynch label CLI choices exist; feature columns are strategy-specific).

| Step | Tool | Output |
|------|------|--------|
| Live signals | `quant-launchpad*` / `quant-swing` | `scan_runs` + `ticker_results` in Postgres |
| Historical signals | `quant-backfill launchpad` / `quant-backfill swing` | Same tables (Saturdays / Fridays) |
| Price cache for labels | `quant-ml warm-cache` | Daily OHLCV parquet (~5y) |
| Forward-return labels | `quant-ml label --strategy launchpad\|swing` | `signal_outcomes` in Postgres |
| Training export | `quant-ml export-features` | Parquet under `data/ml/features/` |
| Model training | `quant-ml train` | LightGBM artifact + `ml_models` registry row |
| Model evaluation | `quant-ml evaluate` | Walk-forward AUC and top-K return metrics |

**Preferred Launchpad path (small universe first):** [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) (`mega_runners` → label → train @ h20).

**Not built yet (Phase 2.5 / Phase 3):** dashboard ML UI, live model inference inside scanners.

---

## 2. Current scope (ops phase)

`docker/crontab` is Launchpad-forward: weekday Launchpad daily + Saturday Launchpad-all are **on**; most breakout/swing/Lynch scan lines are **commented out**. Digests and a swing ML label job may still be present — confirm with `docker exec quant-hub cat /etc/cron.d/quant-hub`.

| Focus | Commands |
|-------|----------|
| Tune Launchpad | `mega_runners` live scan + backfill + `quant-ml … --strategy launchpad` |
| Scale later | Same pipeline with `--universe sp500_index` |

See [ML Foundation § ML phase scope](ML_FOUNDATION.md#ml-phase-scope-current) and [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md).

---

## 3. Pipeline overview

```text
                    ┌─────────────────────────────────────┐
                    │  Weekly OHLCV (10y / 1wk parquet)   │
                    └─────────────────┬───────────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         │                            │                            │
         v                            v                            v
  quant-swing (live)      quant-backfill swing          (future strategies)
         │                            │
         └────────────┬───────────────┘
                      v
            scan_runs + ticker_results
            (full detail JSON per ticker)
                      │
         ┌────────────┴────────────┐
         v                         v
  quant-ml warm-cache        quant-ml export-features
  (daily 5y parquet)                │
         │                         v
         v                  data/ml/features/*.parquet
  quant-ml label
         │
         v
   signal_outcomes
```

---

## 4. Prerequisites

| Requirement | Check |
|-------------|--------|
| Containers running | `docker compose ps` — `quant-hub` + `quant-hub-db` healthy |
| Schema applied | `docker exec quant-hub quant-hub init-db` |
| Weekly swing cache | Populated automatically on first swing/backfill run |
| Postgres reachable | `docker exec quant-hub quant-hub status` → `Database: OK` |

**Host paths** (bind-mounted from container):

| Path | Contents |
|------|----------|
| `/mnt/fast/quant-data/data/cache/prices/1wk/10y/` | Weekly OHLCV (swing scans & backfill) |
| `/mnt/fast/quant-data/data/cache/prices/1d/5y/` | Extended daily OHLCV (ML labels) |
| `/mnt/fast/quant-data/data/cache/prices/1d/2y/` | Breakout daily cache (label fallback) |
| `/mnt/fast/quant-data/data/ml/features/` | Exported training Parquet |
| `/mnt/fast/quant-data/backups/` | Manual `pg_dump` backups |

**Logs:**

| Log | Path |
|-----|------|
| ML jobs | `/mnt/fast/quant-data/logs/ml.log` |
| Backfill | `/mnt/fast/quant-data/logs/backfill.log` |
| Cron | `/mnt/fast/quant-data/logs/cron.log` |
| ML phase script | `/mnt/fast/quant-data/logs/ml_phase.log` |

---

## 5. First-time setup (swing sp500)

Run once after a DB cleanup or fresh install:

```bash
# 1. Historical weekly signals (point-in-time, ~6–10 min for 2y of Fridays)
docker exec quant-hub quant-backfill swing --universe sp500_index --since 2024-01-01

# 2. Extended daily prices for labels (~20 min first run)
docker exec quant-hub quant-ml warm-cache --universe sp500_index

# 3. Forward-return labels (~15–20 min for full backfill)
docker exec quant-hub quant-ml label --strategy swing --universe sp500_index --since 2024-01-01

# 4. Export training Parquet
docker exec quant-hub quant-ml export-features --strategy swing --universe sp500_index --since 2024-01-01
```

**One-shot helper** (live scan + warm-cache + label; no backfill):

```bash
docker exec quant-hub bash /app/scripts/ml-phase-swing-sp500-index.sh
```

---

## 6. Ongoing operations

### Weekly (automatic)

1. **Friday 5:45 PM ET** — new swing scan for `sp500_index` upserts `(today, swing, sp500)`.
2. **Saturday 6:00 AM ET** — labels recomputed for the last 90 days of swing sp500 runs.

No action required unless cron fails (check `cron.log`).

### After manual swing scan

```bash
docker exec quant-hub quant-swing --universe sp500_index --no-email
docker exec quant-hub quant-ml label --strategy swing --universe sp500_index --since $(date -d '7 days ago' +%F)
```

### Refresh labels when price cache grows

Re-run labeling after `warm-cache` or when calendar time advances (recent weeks gain forward bars):

```bash
docker exec quant-hub quant-ml label --strategy swing --universe sp500_index --since 2024-01-01
```

### Re-export training data

```bash
docker exec quant-hub quant-ml export-features --strategy swing --universe sp500_index --since 2024-01-01
```

---

## 7. Backfill (`quant-backfill`)

Replays **historical Fridays** using truncated weekly parquet — no lookahead.

**Check coverage before a long run** (shows missing Fridays vs Postgres):

```bash
docker exec quant-hub quant-backfill coverage --universe sp500_index --since 2020-01-01
docker exec quant-hub quant-backfill coverage --universe sp500_index --since 2020-01-01 --until 2023-12-31
```

Example output when 2020–2023 is missing but 2024+ exists:

```text
swing/sp500 range=2020-01-03..2026-06-27 planned=340 existing=131 missing=209
  db_range=2024-01-05..2026-06-27 (131 Fridays in range)
  first_missing=[2020-01-03, 2020-01-10, ... +204 more]
```

**Run backfill** (default `--resume` skips dates already in Postgres; only **missing** weeks are written):

```bash
# Fill 2020–2023 gap without re-scanning 2024+
docker exec quant-hub quant-backfill swing --universe sp500_index --since 2020-01-01 --until 2023-12-31

docker exec quant-hub quant-backfill swing --universe sp500_index --since 2024-01-01
docker exec quant-hub quant-backfill swing --universe sp500_index --since 2024-06-07 --until 2024-06-07 --no-resume
docker exec quant-hub quant-backfill swing --universe sp500_index --since 2020-01-01 --dry-run
```

| Flag | Effect |
|------|--------|
| `--since` | **Required.** First Friday on or after this date |
| `--until` | Last Friday on or before this date (default: today) |
| `--no-resume` | Overwrite dates already in Postgres (default: skip existing) |
| `--dry-run` | Compute only; no DB writes |

**Pre-flight:** `quant-backfill swing` prints `pre-flight: planned=… missing=…` before writing. Progress logs every 25 Fridays in `backfill.log`.

**What gets written:**

- One `scan_runs` row per Friday (`UNIQUE` on `scan_date, strategy_id, universe_id`)
- ~193 `ticker_results` rows per week (full universe detail, not setups-only CSV)
- `metadata.data_provenance.backfill = true`
- `metadata.data_provenance.as_of_price` = last weekly bar date (≤ scan_date)

**Limitations (v1):**

- Uses **today's** sp500 membership for all dates (survivorship bias)
- Only **swing** strategy supported
- Requires existing **10y weekly parquet** (no per-date yfinance re-download)
- Earliest reliable `--since` ≈ **2016** (10y cache minus 60 weekly bars for indicators). **2020-01-01 is supported.**
- **Resume is not the problem** when extending history: if DB starts at 2024, `--since 2020-01-01` still writes 2020–2023. Use `coverage` to confirm missing weeks before/after a run.

---

## 8. Labeling (`quant-ml label`)

Computes forward returns from **daily** OHLCV for every ticker in every matched scan run.

```bash
docker exec quant-hub quant-ml status

docker exec quant-hub quant-ml label --strategy swing --universe sp500_index --since 2024-01-01
docker exec quant-hub quant-ml label --run-id 42
docker exec quant-hub quant-ml label --strategy swing --universe sp500_index \
  --since 2024-01-01 --horizons 5,10,20,63 --threshold 2.0
```

| `label_status` | Meaning |
|----------------|---------|
| `ok` | Forward return computed |
| `no_price` | Ticker missing from daily cache |
| `invalid_anchor` | No trading day strictly after anchor (anchor at cache edge) |
| `insufficient_future_bars` | Not enough future sessions for horizon (recent weeks) |

**Defaults:** horizons `5, 10, 20, 63` trading days; binary label threshold `2.0%`.

**Price cache order:** `data/cache/prices/1d/5y/` (primary) → `1d/2y/` (fallback).

---

## 9. Feature export (`quant-ml export-features`)

Flattens Postgres `detail` JSON into tabular columns for pandas / LightGBM.

```bash
docker exec quant-hub quant-ml export-features --strategy swing --universe sp500_index --since 2024-01-01
docker exec quant-hub quant-ml export-features --strategy swing --universe sp500_index --horizon 10
docker exec quant-hub quant-ml export-features --run-id 42 --per-run
docker exec quant-hub quant-ml export-features --strategy swing --universe sp500_index --no-labels
```

**Output:** `data/ml/features/{strategy}/{universe}/features_{since}_export.parquet`

**Swing columns include:** `swing_score`, `quality_label`, `rsi`, `ema20`, `ema50`, `atr`, `rs_ratio`, `rs_percentile`, `vol_ratio`, `penalty_total`, plus label columns when joined.

**Schema version:** `v2` (`FEATURE_SCHEMA_VERSION` in config). Bump when changing export columns.

---

## 10. Verification

### Quick CLI

```bash
docker exec quant-hub quant-hub status
docker exec quant-hub quant-ml status
```

### Backfill coverage

```sql
SELECT COUNT(*) AS weeks,
       MIN(scan_date) AS first_week,
       MAX(scan_date) AS last_week,
       SUM(actionable_count) AS total_setups
FROM scan_runs
WHERE strategy_id = 'swing' AND universe_id = 'sp500_index';
```

```sql
SELECT scan_date, actionable_count,
       metadata->'data_provenance'->>'backfill' AS backfill,
       metadata->'data_provenance'->>'as_of_price' AS as_of_price
FROM scan_runs
WHERE strategy_id = 'swing' AND universe_id = 'sp500_index'
ORDER BY scan_date DESC
LIMIT 10;
```

### Setups on a specific week

```sql
SELECT tr.ticker, tr.tier, tr.final_score,
       tr.detail->'setup_detail'->>'swing_score' AS swing_score,
       tr.detail->'setup_detail'->>'rs_ratio' AS rs_ratio
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'swing'
  AND sr.universe_id = 'sp500_index'
  AND sr.scan_date = '2025-06-06'
  AND tr.tier IN ('SETUP_LONG', 'SETUP_SHORT')
ORDER BY tr.final_score DESC;
```

### Label quality

```sql
SELECT label_status, COUNT(*)
FROM signal_outcomes so
JOIN scan_runs sr ON sr.id = so.run_id
WHERE sr.strategy_id = 'swing' AND sr.universe_id = 'sp500_index'
GROUP BY label_status;
```

### Training set preview (10d horizon, setups only)

```sql
SELECT sr.scan_date, tr.ticker, tr.tier,
       so.forward_return_pct, so.label_binary
FROM scan_runs sr
JOIN ticker_results tr ON tr.run_id = sr.id
JOIN signal_outcomes so ON so.run_id = sr.id AND so.ticker = tr.ticker
WHERE sr.strategy_id = 'swing'
  AND sr.universe_id = 'sp500_index'
  AND tr.tier = 'SETUP_LONG'
  AND so.horizon_days = 10
  AND so.label_status = 'ok'
ORDER BY sr.scan_date DESC, so.forward_return_pct DESC
LIMIT 20;
```

### Parquet on host

```bash
ls -lh /mnt/fast/quant-data/data/ml/features/swing/sp500/
```

```python
import pandas as pd
df = pd.read_parquet(
    "/mnt/fast/quant-data/data/ml/features/swing/sp500/features_2024-01-01_export.parquet"
)
print(df.shape, df["scan_date"].min(), df["scan_date"].max())
print(df["tier"].value_counts())
```

### Dashboard

Open `http://localhost:5002` → **Swing** → **sp500** → pick a historical **scan date** from the dropdown.

---

## 11. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| All labels `invalid_anchor` | Daily cache ends at scan week; no forward bars | Run `quant-ml warm-cache`; wait for calendar time |
| Many `insufficient_future_bars` | Recent Fridays lack 63d forward history | Expected; use `--horizon 10` or filter `label_status = 'ok'` |
| Many `no_price` | Missing ticker in 5y/2y cache | `quant-ml warm-cache --force-refresh` |
| Backfill `dates_failed > 0` | Corrupt/missing weekly parquet for ticker | Check `backfill.log`; refresh weekly cache via `quant-swing --force-refresh` |
| `quant-ml label` very slow | 131 runs × 193 tickers × 4 horizons | Normal (~15–20 min); filter with `--since` / `--until` |
| Export 0 rows | No matching scan runs for filters | Verify `quant-hub status`; widen date range |
| Dashboard import error on swing guide | Stale container image | `docker compose up -d --build` |

---

## 12. Do not do this on the ML database

| Action | Risk |
|--------|------|
| `TRUNCATE scan_runs` / `full-rescan.sh` | Deletes all signals **and** cascades `signal_outcomes` |
| Restore old backup without planning | Overwrites weeks of backfill + labels |
| Train on `scan_date >= today - 63d` without filtering `label_status` | Incomplete labels skew metrics |
| Shuffle dates randomly in train/test split | Leakage — use walk-forward by `scan_date` |

**Safe:** Re-run `quant-backfill` (upserts), `quant-ml label` (upserts), `quant-ml export-features` (overwrites Parquet).

---

## 13. Backup before major ML work

```bash
mkdir -p /mnt/fast/quant-data/backups
docker exec quant-hub-db pg_dump -U quant quant_hub \
  | gzip > /mnt/fast/quant-data/backups/quant_hub_$(date +%Y%m%d).sql.gz
```

See [Runbook § Backup](RUNBOOK.md#6-backup-and-restore).

---

## 14. CLI quick reference

| Command | Purpose |
|---------|---------|
| `quant-backfill coverage --since YYYY-MM-DD` | Show missing Fridays vs Postgres before backfill |
| `quant-backfill swing --since YYYY-MM-DD` | Historical swing scans |
| `quant-ml warm-cache --universe sp500_index` | Download 5y daily OHLCV |
| `quant-ml label --strategy swing --universe sp500_index` | Compute forward returns |
| `quant-ml export-features --strategy swing --universe sp500_index` | Write training Parquet |
| `quant-ml train --strategy swing --universe sp500_index --since YYYY-MM-DD` | Train LightGBM + register |
| `quant-ml evaluate --model-id N [--walk-forward]` | Holdout or walk-forward metrics |
| `quant-ml models` | List `ml_models` registry |
| `quant-ml status` | `signal_outcomes` counts |
| `quant-hub status` | Scan run summary |

All commands run inside the container:

```bash
docker exec quant-hub <command>
```

---

## 15. Phase 2 — train and evaluate

### Install ML dependencies

The Docker image includes `[ml]` extras (`scikit-learn`, `lightgbm`). For local dev:

```bash
uv pip install -e ".[dev,ml]"
```

Apply schema (includes `ml_models` table):

```bash
docker exec quant-hub quant-hub init-db
```

### Train a swing sp500 model

Trains on **setups only** (`SETUP_LONG` / `SETUP_SHORT`) with `label_status = ok` at the chosen horizon (default 10d). By default the last 26 weekly scan dates are held out for an immediate eval report.

```bash
docker exec quant-hub quant-ml train \
  --strategy swing \
  --universe sp500_index \
  --since 2020-01-01 \
  --horizon 10 \
  --name swing_v1
```

Artifacts land at `data/ml/models/{name}/` (`model.txt` + `features.json`). A row is inserted into `ml_models`.

### Evaluate (holdout or walk-forward)

```bash
# Holdout using registry split date from training
docker exec quant-hub quant-ml evaluate --model-id 1

# Rolling walk-forward (52w train / 13w test)
docker exec quant-hub quant-ml evaluate --model-id 1 --walk-forward

# List registry
docker exec quant-hub quant-ml models
```

Metrics include **AUC**, **precision/recall**, and **mean forward return of top-K setups per week** compared to sorting by `swing_score`.

### Success criteria

- [x] `quant-ml train` registers a model from swing sp500 backfill data
- [x] `quant-ml evaluate --walk-forward` reports metrics on held-out weeks
- [x] Documented comparison: ML top-N vs `swing_score` top-N on 10d forward return (see evaluate output)

---

## 16. Phase 2.5 / Phase 3 roadmap

- Dashboard ML review UI (forward returns on swing tables, coverage charts)
- Live reranker integrated into `quant-swing` output
- Breakout / Lynch models after swing sp500 validated
- Point-in-time universe membership for backfill
- Optional: automated weekly export to cold storage

---

## 17. Further reading

| Doc | Contents |
|-----|----------|
| [ML Foundation](ML_FOUNDATION.md) | Schema, leakage rules, retention policy |
| [Data Model](DATA_MODEL.md) | Postgres tables, cache layout |
| [Swing Scanner](SWING_SCANNER.md) | Setup rules, scoring rubric, `detail` JSON |
| [Analytics Guide](ANALYTICS_GUIDE.md) | Ad-hoc SQL patterns |
