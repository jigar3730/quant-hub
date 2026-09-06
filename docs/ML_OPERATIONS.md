# Machine Learning & MLOps — Operational Documentation

**Audience:** DevOps / Run Team (no prior ML context required)  
**Scope:** Launchpad ML only. Lynch can export feature rows; it has **no trainer**.  
**Production truth:** Live Launchpad and Lynch scans **do not call a trained model**. ML is an **offline research pipeline** (labels → Parquet → LightGBM → walk-forward metrics) used to tune scanner thresholds.  
**Authoritative schedule:** `docker/crontab` (not `docker/jobs.yaml`, which can lag).  
**Last verified against codebase:** 2026-09-05  
**Related:** [ML Foundation](ML_FOUNDATION.md) · [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) · [ML Ops (short)](ML_OPS.md) · [Runbook](RUNBOOK.md) · [Data Model](DATA_MODEL.md)

---

## Critical operating facts

| Fact | Implication |
|------|-------------|
| **No live inference endpoint** | Users never receive model probabilities on the dashboard or in digest email. Scanner scores are rule-based. |
| **No HTTP/gRPC model server** | There is nothing to restart besides `quant-hub` + Postgres. |
| **No automated retrain** | Cron **labels** recent Launchpad runs on Saturday. Training is **manual**. |
| **No drift monitors** | Operators detect issues via logs, `quant-ml status`, and holdout/walk-forward metrics. |
| **Labels cascade with scans** | Deleting `scan_runs` deletes `signal_outcomes` (`ON DELETE CASCADE`). |

If production “ML is broken,” start with: **Postgres up? Cron labeling? Price cache warm? `label_status` mix?** — not “is the model serving?”

---

# 1. ML Architecture & Configuration Overview

## 1.1 What the ML system is

```text
Yahoo OHLCV (yfinance)
    → Parquet caches (2y scan / 5y labels)
    → Launchpad StrategyEngine (eligibility + factors + tiers)
    → Postgres scan_runs + ticker_results.detail JSONB
    → quant-ml label  → signal_outcomes
    → quant-ml export-features / train  → Parquet + LightGBM artifact
    → ml_models registry
```

**Not in this stack:** PyTorch, TensorFlow, ONNX Runtime, MLflow, feature store, model HTTP API, GPU workers, A/B serving, concept-drift service.

## 1.2 Configuration maps

There are **no ML feature flags** and **no model URLs**. Behavior is code constants + CLI flags + env for the database.

### Environment variables

| Variable | Required | Role for ML |
|----------|----------|-------------|
| `DATABASE_URL` | **Yes** | Postgres connection. `config.database_url()` raises if unset. |
| `POSTGRES_PASSWORD` | **Yes** (Compose) | Injected into `DATABASE_URL` for `quant-hub`. |
| `TZ` | Set in Compose | `America/New_York` — cron and scan dates. |
| `SMTP_*` / `EMAIL_*` | Digest only | Unused by `quant-ml`. |

Source of env template: `.env.example`. Cron inherits a subset written by `docker/entrypoint.sh` into `/etc/environment`.

### Python / module constants (`src/quant_hub/config.py`)

```python
ML_DIR = DATA_DIR / "ml"
ML_FEATURES_DIR = ML_DIR / "features"
ML_MODELS_DIR = ML_DIR / "models"
FEATURE_SCHEMA_VERSION = "v4"
DEFAULT_LABEL_HORIZONS = (5, 10, 20, 63)
LABEL_RETURN_THRESHOLD_PCT = 2.0
BENCHMARK_TICKER_FOR_LABELS = "SPY"
ML_LABEL_LOOKBACK_DAYS = 1260          # ~5 calendar years
ML_LABEL_CACHE_SUBDIR = CACHE_DIR / "prices" / "1d" / "5y"
ML_LABEL_CACHE_TTL_HOURS = 8760        # 1 year; refresh via warm-cache
PRICE_CACHE_SUBDIR = CACHE_DIR / "prices" / "1d" / "2y"
CACHE_TTL_HOURS = 24                   # live scan cache
```

Re-exported for ML code in `src/quant_hub/ml/constants.py`.

### CLI defaults (`src/quant_hub/cli/ml.py`)

| Command | Notable defaults |
|---------|------------------|
| `quant-ml label` | Horizons `5,10,20,63`; binary threshold **+2%**; optional `--strategy` `launchpad` or `lynch` |
| `quant-ml export-features` | Label join horizon **10** if `--horizon` omitted and labels included |
| `quant-ml warm-cache` | Universe default `sp500_index` |
| `quant-ml train` | Strategy **launchpad only**; universe default `sp500_index`; horizon default **10**; setups-only (Tier 1–3); top-K **5** |
| `quant-ml evaluate` | `--train-weeks 52`, `--test-weeks 13`, top-K **5** |

**Operator pitfall:** Training default horizon is **10**. Launchpad research often uses **`--horizon 20`**. Always pass the horizon you labeled and intend to evaluate.

### LightGBM hyperparameters (`src/quant_hub/ml/train.py`)

```python
DEFAULT_LGBM_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "verbosity": -1,
    "num_leaves": 15,
    "learning_rate": 0.05,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "min_child_samples": 5,
    "seed": 42,
}
# num_boost_round defaults to 100 (popped from params before lgb.train)
```

There is **no** hyperparameter config file. Override only by passing `train_params` in code (the CLI does not expose a params JSON flag).

### Scanner knobs that change *features* (not the model)

Live scores (and therefore training features) come from Launchpad rules in `config.py` (`LAUNCHPAD_*`) and `src/quant_hub/scoring/launchpad.py`. Changing these **without** re-backfill / re-scan **invalidates** comparison of old vs new models.

| Constant | Effect on ML |
|----------|----------------|
| `LAUNCHPAD_TIER1_NORMALIZED_MIN` (80) | Tier 1 gate; training `setups_only` includes Tiers 1–3 |
| `LAUNCHPAD_TIER2_NORMALIZED_MIN` (65) | Tier 2 vs 3 |
| `LAUNCHPAD_MIN_HISTORY_DAYS` (200) | Eligibility filter |
| `LAUNCHPAD_MIN_AVG_VOLUME` (750_000) | Eligibility filter |
| `LAUNCHPAD_PROXIMITY_*` | Eligibility + `resistance_distance_pct` analog |
| ATR / volume dry-up / VCP thresholds | Factor raw values mapped into features |

Tier 1 also requires MACD zero-line factor score ≥ **25** (`MACD_TIER1_SCORE` in `strategies/launchpad/tiers.py`).

### Universe / data files

| Asset | Path (repo) | Live Docker volume |
|-------|-------------|--------------------|
| Universe registry | `data/universes.json` | `/mnt/fast/quant-data/data/universes.json` |
| Ticker lists | `data/universes/*.txt` | `/mnt/fast/quant-data/data/universes/` |
| Schema bootstrap | `src/quant_hub/infrastructure/postgres/schema.sql` | Applied by `quant-hub init-db` on container start |

The container mounts **volume** data, not the git tree. After editing universes in git, copy them to the volume (see [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md)).

### Model “endpoints”

| Kind | Exists? |
|------|---------|
| REST / gRPC inference | **No** |
| In-process `Booster.predict` | **Yes**, only in `MLTrainService` (holdout) and `MLEvaluateService` |
| Dashboard model picker | **No** |

Artifact layout after train:

```text
/app/data/ml/models/{name}/
    model.txt          # LightGBM dump
    features.json      # feature_columns + strategy/universe/horizon metadata
```

Host: `/mnt/fast/quant-data/data/ml/models/{name}/`.

Default `name`: `{strategy}_{universe}_h{horizon}_{YYYYMMDD}` (today’s date). **`ml_models.name` is UNIQUE** — a second train on the same calendar day with the same default name **will fail** at insert. Use `--name` or archive/rename the old row.

## 1.3 Dependencies & runtime

### Python and packages

| Item | Value |
|------|--------|
| Python | **3.12** (`requires-python = ">=3.12"`, image `python:3.12-slim`) |
| Core numeric | `numpy>=2`, `pandas>=2.2`, `pyarrow>=18` |
| ML extra (`.[ml]`) | `scikit-learn>=1.5`, `lightgbm>=4.0` |
| Market data | `yfinance>=0.2.40` |
| Persistence | `psycopg[binary]>=3.2`, Postgres **16** |

Docker installs extras: `uv pip install --system -e .[dev,viz,ml]` (`docker/Dockerfile`). Host venv without `[ml]` can run scans but **cannot train**.

`libgomp1` is installed in the image for LightGBM OpenMP.

### Hardware

| Resource | Production compose | ML implication |
|----------|-------------------|----------------|
| GPU | **None** | CPU-only LightGBM |
| Postgres | `shared_buffers=1GB`, `work_mem=32MB`, `effective_cache_size=3GB` | Label/export SQL; not GPU |
| App container | No CPU/memory limits in `docker-compose.yml` | Train/evaluate share the dashboard+cron container |
| Disk | `/mnt/fast/quant-data/{data,logs,postgres}` | 5y Parquet + models + DB |

**Do not** run a large `sp500_index` train concurrently with weekday 5:10–5:40 PM ET Launchpad+digest if the box is already CPU-bound; training is a batch job — schedule it off-peak.

### Model artifacts

| Artifact | Format | Who writes it |
|----------|--------|----------------|
| Feature Parquet | Apache Parquet via pandas | `MLExportService` |
| LightGBM model | `model.txt` | `save_model_artifact` |
| Feature schema sidecar | `features.json` | same |
| Registry row | `ml_models` | `MlModelsRepository.insert_model` |

Feature schema version string: **`v4`**. Changing `LAUNCHPAD_FEATURE_COLUMNS` without bumping `FEATURE_SCHEMA_VERSION` will confuse operators comparing models.

## 1.4 Directory layout (ML-related)

### Code

```text
src/quant_hub/cli/ml.py                          # quant-ml CLI
src/quant_hub/config.py                          # paths, horizons, thresholds
src/quant_hub/ml/
  constants.py                                   # schema v4, feature names, label statuses
  labels.py                                      # forward-return math (no lookahead)
  features.py                                    # JSONB → flat columns
  training_set.py                                # SQL join + filters + embargo
  walk_forward.py                                # chronological folds, purge, embargo
  train.py                                       # LightGBM fit/save/load
  evaluate.py                                    # AUC, top-K vs score baseline
  backfill_dates.py                              # Saturday PIT date helpers
src/quant_hub/application/
  ml_cache_service.py                            # warm 5y cache
  ml_label_service.py
  ml_export_service.py
  ml_train_service.py
  ml_evaluate_service.py
  launchpad_backfill_service.py                  # PIT historical scans (training fuel)
src/quant_hub/infrastructure/postgres/
  schema.sql                                     # signal_outcomes, ml_models
  outcomes_repository.py
  ml_models_repository.py
src/quant_hub/strategies/launchpad/              # live + backfill scoring (feature source)
src/quant_hub/scoring/launchpad.py
src/quant_hub/factors/launchpad.py
src/quant_hub/engine/runner.py                   # StrategyEngine
tests/unit/test_training_set.py
tests/unit/test_ml_features.py
tests/unit/test_ml_backfill_dates.py
```

### Runtime paths (container → host)

| Container | Host |
|-----------|------|
| `/app/data/cache/prices/1d/2y/` | `/mnt/fast/quant-data/data/cache/prices/1d/2y/` |
| `/app/data/cache/prices/1d/5y/` | `/mnt/fast/quant-data/data/cache/prices/1d/5y/` |
| `/app/data/ml/features/` | `/mnt/fast/quant-data/data/ml/features/` |
| `/app/data/ml/models/` | `/mnt/fast/quant-data/data/ml/models/` |
| `/app/logs/ml.log` | `/mnt/fast/quant-data/logs/ml.log` |
| `/app/logs/cron.log` | `/mnt/fast/quant-data/logs/cron.log` |
| `/app/logs/backfill.log` | `/mnt/fast/quant-data/logs/backfill.log` |

Feature export path pattern:

```text
data/ml/features/{strategy_id}/{universe_id}/features_{scan_date}_export_h{N}.parquet
data/ml/features/{strategy_id}/{universe_id}/features_run_{run_id}_h{N}.parquet   # --per-run
```

### Tests

Unit coverage exists for feature extraction, training-set filtering, and backfill dates. There is **no** CI pipeline for ML (gap H6 in [Architecture Gaps](ARCHITECTURE_GAPS.md)).

---

# 2. ML System Mechanics & Data Flow

## 2.1 Data ingestion & preprocessing

### Raw market data

1. **Source:** Yahoo Finance via `yfinance` (`infrastructure/market/yfinance_prices.py`). Sole provider (gap P1).
2. **Live scans:** ~2y daily bars, cache TTL **24h**, directory `prices/1d/2y`.
3. **ML labels / backfill:** ~**1260** calendar days (~5y), TTL **8760h**, directory `prices/1d/5y`.
4. **Sanitization:** `ParquetCache.read` drops incomplete last bars (`data/quality.py`). Stale last bars force refresh when `max_bar_age_days` is used.

Warm the label cache:

```bash
docker exec quant-hub quant-ml warm-cache --universe most_actives
# force Yahoo refetch:
docker exec quant-hub quant-ml warm-cache --universe most_actives --force-refresh
```

Always includes **SPY** (`BENCHMARK_TICKER_FOR_LABELS`) for excess-return labels.

Label service read order: **5y cache first**, then fallback to **2y** scan cache (`MLLabelService._read_prices`). Missing both → `label_status = no_price`.

### Launchpad scan (feature source)

This is **not** a learned preprocessor. It is a deterministic technical engine:

1. Resolve universe (`universes.json` + ticker files).
2. Download/read OHLCV; compute **SPY market regime** (`regime/market.py`): `strong` (×1.0), `neutral` (×0.85), `weak` (×0.6). Stored on **`scan_runs`**.
3. Per ticker: eligibility filters (history, price ≥ $10, volume, EMA200 trend, proximity to EMA50/support). Failures → `tier = filtered`.
4. Factors (raw + scores): squeeze, tightness percentile, volume vacuum, trend proximity, MACD zero-line.
5. Aggregate (`strategies/launchpad/aggregate.py`): raw sum of four score factors (max 100), normalize 0–100. **Ticker `regime_multiplier` is currently hardcoded to `1.0`**; `final_score` equals `normalized_score`. Run-level regime is still persisted and **is** used as ML feature `market_regime_multiplier`.
6. Tiers: filtered / Tier 3 / Tier 2 (≥65) / Tier 1 (≥80 **and** MACD ≥ 25).
7. Persist `scan_runs` + `ticker_results.detail` JSONB (idempotent same-day upsert).

### Point-in-time historical fuel

`quant-backfill launchpad` replays **Saturday** scans with prices **truncated to each scan date** (`truncate_daily_to_date`) so features do not see future bars. Version constant: `BACKFILL_VERSION = "v1"`.

Universes in production cron (weekday + Saturday) as of `docker/crontab`: `most_actives`, `large_cap_growth`, `small_cap_growth`, `mid_cap_growth`. Research often starts on `mega_runners`.

### Feature flattening (`ml/features.py`)

Only values **already in the scan payload** are exported (leakage rule). Launchpad mapping:

| Training column (`LAUNCHPAD_FEATURE_COLUMNS`) | Payload source |
|-----------------------------------------------|----------------|
| `final_score` | `summary.final_adjusted_score` |
| `volatility_compression_ratio` | `scores.squeeze_intensity.raw.squeeze_ratio` |
| `relative_strength_rank` | `scores.tightness_percentile.raw.tightness_rank_pct` |
| `volume_rs_score` | `scores.volume_vacuum_depth.raw.rvol` |
| `resistance_distance_pct` | `scores.trend_proximity_match.raw.pct_distance` |
| `market_regime_multiplier` | `scan_runs.regime_multiplier` (else summary) |

Export also writes diagnostic columns (`normalized_score`, per-factor `score_*`) that are **not** in the LightGBM feature list.

Lynch export maps PEG/PE/growth/etc. **Training raises** `ValueError` if `strategy_id != "launchpad"`.

### Training-set filters (`ml/training_set.py`)

Applied in order:

1. Optional **setups_only** (default): keep `tier ∈ {Tier 1, Tier 2, Tier 3}`; drop `filtered`.
2. Keep `label_status == ok` only.
3. Drop null `label_binary`.
4. **Per-ticker embargo:** after keeping a signal at date T, drop same-ticker rows through **T+5 business days** (`MIN_SIGNAL_EMBARGO_TRADING_DAYS`).
5. Drop rows with any non-numeric / missing feature in `LAUNCHPAD_FEATURE_COLUMNS`.

CLI `--all-tiers` includes filtered rows (usually worse class balance).

## 2.2 Inference pipeline

### Real-time / online inference

**Not implemented.** Gap P2. Live path:

```text
User / cron → quant-launchpad* → StrategyEngine → Postgres → dashboard / digest
```

No `load_model_artifact` on this path.

### Batch “inference” (research only)

Two batch prediction paths exist; both are **evaluation**, not product serving.

#### A. Holdout after train (`MLTrainService`)

1. Build training frame for `--since` / `--until` / `--horizon`.
2. Chronological split: if ≥26 distinct scan dates, default split = **26th-from-last** date; else midpoint; or `--split-date`.
3. Fit LightGBM on train dates **strictly before** split.
4. `booster.predict(X_test)` → probability-like scores (binary objective).
5. Metrics vs **rule-based `final_score`** top-K weekly return.
6. Write artifact + `ml_models` row (`status='active'`).

#### B. `quant-ml evaluate`

**Registered model (`--model-id`):** load `artifact_path/model.txt` + `features.json`. Rebuild the same strategy/universe/horizon frame. Score rows on/after `eval_split_date` (or all rows if missing). Merge results into `ml_models.metrics.evaluation`.

**Walk-forward (`--walk-forward`):** **does not use the saved booster for fold predictions.** For each fold it **retrains a new LightGBM** on purged train dates, then predicts the test window. This measures **protocol stability**, not the frozen artifact’s production score.

Purge: drop train dates whose label horizon (calendar approximation `ceil(max(horizon,5)*7/5)` days) would overlap the test start (`purge_train_dates`).

Fold construction: sorted unique scan dates; windows of `train_weeks` then `test_weeks`; step = `test_weeks`. If fewer dates than `train_weeks + test_weeks`, **zero folds** (empty metrics).

### Step-by-step: one labeled example → score (evaluate holdout)

1. SQL join `scan_runs ⋈ ticker_results ⋈ signal_outcomes` for one `horizon_days`.
2. `extract_features` → six numeric columns.
3. LightGBM `Booster.predict` → float in `[0,1]` (not calibrated).
4. Metrics (not product output):
   - **AUC** (`sklearn.metrics.roc_auc_score`) if both classes present.
   - **Precision/recall** at **0.5** threshold (`evaluate.py` — named `precision_at_k` / `recall_at_k` in the dict but computed as 0.5-threshold classification, **not** ranking@K).
   - **Mean forward return of top-K by model score per `scan_date`**, averaged across dates.
   - Same top-K using `final_score` (or `normalized_score`) as **baseline**.
   - `return_lift_vs_baseline` = ML top-K return − score top-K return.

## 2.3 Post-processing & business logic

| Layer | Behavior |
|-------|----------|
| **Product responses** | Tiers, digest lists, dashboard ranks use **Launchpad `final_score` / eligibility**, not ML. |
| **Binary label** | `forward_return_pct >= LABEL_RETURN_THRESHOLD_PCT` (default **2.0**). Not excess vs SPY. Excess is stored but **not** the training target. |
| **0.5 predict threshold** | Used only in evaluate precision/recall. **Not** a trading gate. |
| **Top-K** | Default **5** names per scan date for return metrics. |
| **Fallbacks** | Empty training set → train returns `model_id=None`, CLI exit 1. Evaluate empty set → `metrics.error = "empty dataset"`. Missing SPY cache → excess returns null, stock labels still compute if ticker prices exist. Factor compute exception → ticker `compute_error`, ineligible. |
| **Yahoo failure** | Incomplete prices → filters `no_price_data` / `insufficient_history`; labels `no_price`. No secondary vendor. |

Label statuses (`ml/constants.py`):

| `label_status` | Meaning | Trainable? |
|----------------|---------|------------|
| `ok` | Full horizon path computed | **Yes** |
| `no_price` | No OHLCV in 5y or 2y cache | No |
| `invalid_anchor` | No bars **strictly after** anchor | No |
| `insufficient_future_bars` | Fewer than `horizon_days` future sessions | No — **expected for recent scans** |
| `pending` | Schema default; should not remain after a label job | No |

**Label geometry (`ml/labels.py`):**

1. Anchor = provenance `as_of_price`, else `scan_date`.
2. Entry = **first close strictly after** anchor (never same-day).
3. Exit = close after `horizon_days` **trading** rows.
4. Path max gain / max drawdown over that window.
5. SPY same window for excess.

Re-running `quant-ml label` **upserts**; recent `insufficient_future_bars` become `ok` as bars arrive. That is the intended Saturday job.

---

# 3. MLOps & Operational Runbook

## 3.1 Model lifecycle & retraining

### What is automated

| When (ET) | Job (from `docker/crontab`) | Writes |
|-----------|-----------------------------|--------|
| Sat 07:00 | `quant-ml label --strategy launchpad --universe most_actives --since $(date -d '90 days ago' +%Y-%m-%d)` | `signal_outcomes` upsert |
| Sat 07:12 | same, `large_cap_growth` | |
| Sat 07:24 | same, `small_cap_growth` | |
| Sat 07:36 | same, `mid_cap_growth` | |

**Not scheduled:** `warm-cache`, `export-features`, `train`, `evaluate`, backfill.

Weekday Launchpad scans (17:10–17:25 ET) create the **signals** that Saturday labeling scores once enough future bars exist (5–63 sessions depending on horizon).

### Manual promotion path (research)

```bash
# 1) Ensure scans exist (live or backfill)
docker exec quant-hub quant-backfill coverage --strategy launchpad --universe mega_runners --since YYYY-MM-DD
docker exec quant-hub quant-backfill launchpad --universe mega_runners --since YYYY-MM-DD

# 2) Prices for forward returns
docker exec quant-hub quant-ml warm-cache --universe mega_runners

# 3) Labels (repeatable)
docker exec quant-hub quant-ml label --strategy launchpad --universe mega_runners --since YYYY-MM-DD

# 4) Optional Parquet for analysis
docker exec quant-hub quant-ml export-features --strategy launchpad --universe mega_runners --since YYYY-MM-DD --horizon 20

# 5) Train (registers ml_models + files)
docker exec quant-hub quant-ml train --strategy launchpad --universe mega_runners --since YYYY-MM-DD --horizon 20 --name launchpad_mega_h20_manual

# 6) Walk-forward protocol check
docker exec quant-hub quant-ml evaluate --model-id <id> --walk-forward --train-weeks 52 --test-weeks 13
```

### Validation gates (human, not enforced in code)

Use before treating a model as “good enough to retune scanner constants”:

- Majority of eligible historical rows `label_status=ok` (except the last ~horizon days).
- Walk-forward **mean AUC** and **mean return lift vs `final_score` top-K** both informative (not one noisy mega_runners fold).
- Feature schema `v4` matches current `LAUNCHPAD_FEATURE_COLUMNS`.
- Enough **setup** rows (guide: thousands after leaving `mega_runners`; small universes only prove plumbing).

There is **no** approval workflow, staging registry, or “production model” pointer. `status` is `active` or `archived` in SQL; **no CLI archives a model**. New trains are additional `active` rows.

### Updating scanner from ML

Offline loop only: inspect gain importance + confusion/top-K → change `LAUNCHPAD_*` → rebuild image → re-scan or `--no-resume` backfill → relabel → retrain → compare holdout. Documented in [LAUNCHPAD_ML_GUIDE.md](LAUNCHPAD_ML_GUIDE.md) §7.

## 3.2 Monitoring & metrics

### Logs

| File | Content |
|------|---------|
| `/mnt/fast/quant-data/logs/ml.log` | All `quant-ml` CLI (`setup_logging("ml.log")`) |
| `/mnt/fast/quant-data/logs/cron.log` | Saturday label jobs + other cron |
| `/mnt/fast/quant-data/logs/backfill.log` | Historical scan jobs |
| stdout of `docker exec` | Same INFO lines |

Format: `%(asctime)s %(levelname)s %(name)s: %(message)s`. **No** Prometheus, OpenTelemetry, or structured JSON metrics (gap: architecture H1 / engineering list).

### Health commands

```bash
docker compose ps
docker exec quant-hub quant-hub status
docker exec quant-hub quant-ml status
docker exec quant-hub quant-ml models --strategy launchpad --limit 20
```

`quant-ml status` prints global `signal_outcomes` counts by `label_status` (all strategies/universes mixed).

### SQL checks

```sql
-- Label health by Launchpad universe
SELECT sr.universe_id, so.label_status, COUNT(*)
FROM signal_outcomes so
JOIN scan_runs sr ON sr.id = so.run_id
WHERE sr.strategy_id = 'launchpad'
GROUP BY sr.universe_id, so.label_status
ORDER BY 1, 2;

-- Recent Saturday label freshness
SELECT MAX(computed_at) AS last_label, COUNT(*) 
FROM signal_outcomes;

-- Registry
SELECT id, name, universe_id, horizon_days, status, created_at,
       metrics->'holdout'->>'auc' AS holdout_auc,
       metrics->'evaluation'->>'mean_auc' AS wf_mean_auc
FROM ml_models
ORDER BY created_at DESC
LIMIT 20;
```

### What is *not* monitored

- Data drift (PSI, KS on features)
- Concept drift (rolling AUC in prod)
- Prediction volume / latency (no serving)
- Model staleness alerts
- Cache hit rate
- Yahoo rate-limit as a first-class metric

**Failure modes you *can* see:**

| Signal | Likely cause |
|--------|----------------|
| Cron `quant-ml label` missing from `cron.log` | Container/cron down; crontab not installed |
| Spike in `no_price` | Cold 5y cache; Yahoo outage; ticker rename |
| Spike in `insufficient_future_bars` on **old** dates | Truncated/corrupt Parquet; lookback too short |
| Persistent `insufficient_future_bars` on **last 3 months** for h63 | Normal until 63 sessions elapse |
| Empty train | No setup tiers, no `ok` labels, embargo wiped small universe |
| Unique violation on `ml_models.name` | Same default name same day |
| Dashboard unchanged after train | **Expected** — inference not wired |

## 3.3 Troubleshooting & maintenance

### Common failures

| Symptom | Check | Fix |
|---------|--------|-----|
| `Database unreachable` | `DATABASE_URL`, `quant-hub-db` healthy | Fix `.env`; `docker compose up -d` |
| `Unknown universe` | Volume vs git `universes.json` | Copy files to `/mnt/fast/quant-data/data/` |
| Labels all `insufficient_future_bars` | Warm-cache; horizon vs calendar | `quant-ml warm-cache`; wait or use h5/h10 |
| Labels `no_price` | `ls` 5y parquet; Yahoo | `warm-cache --force-refresh` then relabel |
| Empty training set | Tiers + labels | Confirm backfill + `setups_only`; `quant-ml status` |
| Export 0 rows | Filters on CLI | Confirm `scan_runs` for strategy/universe/dates |
| Train CLI exit 1, `model_id=None` | Empty frame | See training_set drop counters in logs |
| Walk-forward empty folds | Too few weekly dates | Lower `--train-weeks` / `--test-weeks` or extend backfill |
| Unstable AUC | Small n | Do not retune scanner; scale universe |
| Code change not in container | Image stale | `docker compose up -d --build quant-hub` |
| Cron schedule ≠ this doc | Someone edited crontab | **Trust installed** `/etc/cron.d/quant-hub` inside container |

Inspect installed cron:

```bash
docker exec quant-hub cat /etc/cron.d/quant-hub
```

### Fallback behaviors (production product)

When ML is degraded, **the application already falls back**: Launchpad continues to score with rules. There is no ML circuit breaker because ML is not on the request path.

If **Yahoo** is down: scans degrade (`no_price_data`); do not delete historical `scan_runs` to “retry” — same-day upsert overwrites; history is needed for labels.

### Rollback to a previous model artifact

There is **no serving pointer**, so rollback is **registry + files** for the next evaluate/train comparison (and for any future inference hook).

1. List models:

   ```bash
   docker exec quant-hub quant-ml models --strategy launchpad --universe mega_runners
   ```

2. Confirm files exist:

   ```bash
   docker exec quant-hub ls -la /app/data/ml/models/<older_name>/
   # expect model.txt and features.json
   ```

3. Re-evaluate the old artifact without depending on a new train:

   ```bash
   docker exec quant-hub quant-ml evaluate --model-id <old_id>
   # or:
   docker exec quant-hub quant-ml evaluate --artifact-path /app/data/ml/models/<older_name>
   ```

4. Mark models in SQL (no CLI):

   ```sql
   -- Prefer older model as the research baseline
   UPDATE ml_models SET status = 'archived' WHERE id = <new_bad_id>;
   UPDATE ml_models SET status = 'active' WHERE id = <old_good_id>;
   ```

5. If files were overwritten because **`name` collided**, restore from backup of `/mnt/fast/quant-data/data/ml/models/` (there is **no** model versioning besides unique names + `id`). **Always pass `--name` in production trains.**

6. Scanner-rule rollback is a **code revert + rebuild**, not an ML artifact swap. Historical `ticker_results` keep the scores from the engine version that wrote them.

### Standard maintenance

| Cadence | Action |
|---------|--------|
| Weekly (Sat AM) | Confirm four label jobs in `cron.log`; `quant-ml status` not dominated by `no_price` |
| After universe membership change | `warm-cache` for that universe; optional relabel `--since` |
| After Launchpad scoring code change | Rebuild image; backfill `--no-resume` only for dates that must match new rules; relabel; new `--name` train |
| Before large backfill | `pg_dump` Postgres volume (see [RUNBOOK.md](RUNBOOK.md)); disk space on `/mnt/fast` |
| Cache eviction | Safe to delete Parquet; labels become `no_price` until `warm-cache` + relabel. **Do not truncate `scan_runs`.** |
| Retention | No automated purge. Destructive cleanup cascades labels. Backup first. |

### Postgres backup (ML-critical tables)

```bash
docker exec quant-hub-db pg_dump -U quant quant_hub \
  -t scan_runs -t ticker_results -t signal_outcomes -t ml_models \
  > /mnt/fast/quant-data/backups/ml_$(date +%F).sql
```

Restore drills are **not** automated (gap H2).

### Guardrails (non-negotiable)

1. Never shuffle dates for train/test.
2. Never train on `label_status != ok`.
3. Never use future prices in features (export from stored JSONB only).
4. Do not truncate `scan_runs`.
5. Do not treat mega_runners metrics as production edge.
6. Do not wire live inference without walk-forward evidence and an explicit product decision (gap P2).

---

## Appendix A — `quant-ml` command cheat sheet

```bash
quant-ml warm-cache [--universe ID] [--force-refresh]
quant-ml label [--run-id N] [--strategy launchpad|lynch] [--universe ID]
         [--since YYYY-MM-DD] [--until YYYY-MM-DD]
         [--horizons 5,10,20,63] [--threshold 2.0]
quant-ml export-features [...same filters...] [--horizon N] [--no-labels] [--per-run]
quant-ml train --since YYYY-MM-DD [--until] [--universe] [--horizon 10]
         [--split-date] [--name] [--all-tiers] [--top-k 5]
quant-ml evaluate (--model-id N | --artifact-path DIR)
         [--walk-forward] [--train-weeks 52] [--test-weeks 13] [--json]
quant-ml models [--strategy] [--universe] [--status active|archived] [--limit 20]
quant-ml status
```

Exit codes: **1** if DB down, label processed zero runs (unless `--run-id`), export wrote zero rows, train created no `model_id`, or evaluate metrics contain `error`.

## Appendix B — Schema (excerpt)

From `schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS signal_outcomes (
    run_id BIGINT NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
    ticker VARCHAR(16) NOT NULL,
    horizon_days INT NOT NULL,
    anchor_date DATE NOT NULL,
    forward_return_pct DOUBLE PRECISION,
    forward_max_gain_pct DOUBLE PRECISION,
    forward_max_drawdown_pct DOUBLE PRECISION,
    spy_forward_return_pct DOUBLE PRECISION,
    excess_return_pct DOUBLE PRECISION,
    label_binary BOOLEAN,
    label_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, ticker, horizon_days)
);

CREATE TABLE IF NOT EXISTS ml_models (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,
    strategy_id VARCHAR(32) NOT NULL,
    universe_id VARCHAR(64) NOT NULL,
    horizon_days INT NOT NULL,
    feature_schema_version VARCHAR(16) NOT NULL,
    model_type VARCHAR(64) NOT NULL,  -- lightgbm_classifier
    train_params JSONB,
    metrics JSONB,
    feature_columns JSONB,
    artifact_path TEXT NOT NULL,
    train_since DATE,
    train_until DATE,
    eval_split_date DATE,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Appendix C — Known doc drift

Older guides still mention Saturday labeling of `sp500_index` at 6:00 AM. **Current `docker/crontab` labels four growth/actives universes at 07:00–07:36 ET.** Always verify the file in the running container. `docker/jobs.yaml` is a **reference** and may not match cron (e.g. digest times, universes).
