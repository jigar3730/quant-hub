# Launchpad + Mega Runners — Operator Manual

**Audience:** Operators tuning Launchpad on a small universe before scaling  
**Last updated:** 2026-07-19  
**Related:** [Launchpad Scanner](LAUNCHPAD_SCANNER.md) · [ML Ops](ML_OPS.md) · [ML Foundation](ML_FOUNDATION.md) · [Runbook](RUNBOOK.md)

---

## 1. Goal

Use a **small, intentional universe** (`mega_runners`) to:

1. Run live Launchpad scans  
2. Backfill multi-year Saturday history  
3. Label forward returns and export ML features  
4. Train / evaluate a LightGBM model  
5. Use model insights to **tune scanner thresholds** (offline — live scan inference is not wired yet)

When the pipeline and signal quality look solid, expand the same commands to `sp500_index` (or other universes).

---

## 2. Prerequisites

| Check | Command / path |
|-------|----------------|
| Stack up | `docker compose ps` — `quant-hub` + `quant-hub-db` healthy |
| Schema | `docker exec quant-hub quant-hub init-db` |
| DB empty or ready | `docker exec quant-hub quant-hub status` |
| Universe on **live volume** | Host: `/mnt/fast/quant-data/data/universes/` (not only the git `data/` tree) |

### Sync universe files to the live volume

The container mounts `/mnt/fast/quant-data/data` → `/app/data`. After editing tickers in the repo:

```bash
cp /opt/stacks/quant-hub/data/universes.json /mnt/fast/quant-data/data/universes.json
cp /opt/stacks/quant-hub/data/universes/mega_runners.txt /mnt/fast/quant-data/data/universes/mega_runners.txt
docker exec quant-hub quant-universe show mega_runners
```

Current `mega_runners` tickers (edit the `.txt` file to change):

```text
PLTR, HOOD, TSLA, COIN, IREN, NKE, LULU, SMCI
```

### Host vs container paths

| Host | Container |
|------|-----------|
| `/mnt/fast/quant-data/data/...` | `/app/data/...` |
| `/mnt/fast/quant-data/logs/...` | `/app/logs/...` |

All commands below use `docker exec quant-hub ...` unless you install the package on the host with `DATABASE_URL` set.

---

## 3. Run Launchpad on mega_runners (live)

```bash
# One-shot scan (persists to Postgres, uses daily price cache)
docker exec quant-hub quant-launchpad --universe mega_runners --cache --report both

# Same workflow as weekday cron (no email)
docker exec quant-hub quant-launchpad-daily --universe mega_runners --no-email
```

Inspect results:

```bash
docker exec quant-hub quant-hub status
docker exec quant-hub quant-hub report --strategy launchpad --universe mega_runners
```

Dashboard: open `http://<host>:5002` → Launchpad → universe `mega_runners`.

---

## 4. Backfill historical Saturdays

Launchpad backfill replays **point-in-time Saturday** scans on **~5y daily** OHLCV (truncated to each scan date). Earliest reliable date is printed by coverage (~`2021-07-29` with the 5y cache + 200-bar minimum).

### Preview coverage

```bash
docker exec quant-hub quant-backfill coverage \
  --strategy launchpad \
  --universe mega_runners \
  --since 2021-07-29
```

### Run backfill

```bash
docker exec quant-hub quant-backfill launchpad \
  --universe mega_runners \
  --since 2021-07-29
```

Useful flags:

| Flag | Meaning |
|------|---------|
| `--until YYYY-MM-DD` | Stop at this date (default: today) |
| `--no-resume` | Recompute dates already in Postgres |
| `--dry-run` | Score only; no DB writes |
| `--all-universes` | Every stock-mode universe (slow; skip for mega_runners work) |

Logs: `/mnt/fast/quant-data/logs/backfill.log`.

---

## 5. Generate ML training data

Pipeline:

```text
scan_runs + ticker_results  →  warm-cache (5y daily)  →  label  →  export-features / train
```

### 5.1 Warm the 5y daily price cache

Required before labeling (forward returns need future bars after each scan).

```bash
docker exec quant-hub quant-ml warm-cache --universe mega_runners
```

### 5.2 Label forward returns

Horizons default to **5, 10, 20, 63** trading days. Binary label = forward return ≥ **+2%**.

```bash
docker exec quant-hub quant-ml label \
  --strategy launchpad \
  --universe mega_runners \
  --since 2021-07-29
```

Check:

```bash
docker exec quant-hub quant-ml status
```

### 5.3 Export feature Parquet (optional but useful)

```bash
# Prefer h20 for Launchpad (best short-horizon edge in early QA)
docker exec quant-hub quant-ml export-features \
  --strategy launchpad \
  --universe mega_runners \
  --since 2021-07-29 \
  --horizon 20
```

Files land under (host):

`/mnt/fast/quant-data/data/ml/features/launchpad/mega_runners/features_*_h20.parquet`

If you mount the repo instead of the volume for a one-off job, paths may appear under `/opt/stacks/quant-hub/data/ml/...` — prefer the volume for production artifacts.

### Feature columns (schema v4)

| Feature | Source in scan payload |
|---------|------------------------|
| `final_score` | `summary.final_adjusted_score` |
| `volatility_compression_ratio` | `scores.squeeze_intensity.raw.squeeze_ratio` |
| `relative_strength_rank` | `scores.tightness_percentile.raw.tightness_rank_pct` |
| `volume_rs_score` | `scores.volume_vacuum_depth.raw.rvol` |
| `resistance_distance_pct` | `scores.trend_proximity_match.raw.pct_distance` (distance to support/EMA) |
| `market_regime_multiplier` | run `regime_multiplier` |

Training keeps **Tier 1 / 2 / 3** only when `setups_only` is on (default). Filtered rows are dropped. A **≥5 trading-day per-ticker embargo** is applied when building the training frame to reduce overlapping signals.

---

## 6. Train and evaluate a model

### Train

```bash
docker exec quant-hub quant-ml train \
  --strategy launchpad \
  --universe mega_runners \
  --since 2021-07-29 \
  --horizon 20
```

Notes:

- Default horizon for train is **10** if you omit `--horizon`; for Launchpad prefer **20**.
- Small universes (~200 setup rows) are enough to **validate the pipeline**, not enough for a production model. Expect noisy holdout metrics until you scale the universe.
- Artifact + registry row: `quant-ml models --strategy launchpad`

```bash
docker exec quant-hub quant-ml models --strategy launchpad --universe mega_runners
```

### Walk-forward evaluate

```bash
docker exec quant-hub quant-ml evaluate \
  --model-id <id> \
  --walk-forward \
  --train-weeks 52 \
  --test-weeks 13
```

Fold training uses **purge/embargo** so label horizons do not leak into the test window.

---

## 7. How to use ML to tune the scanner

**Live Launchpad scans do not call the model yet.** Tuning is an offline loop:

```text
Train / evaluate
    → read feature importance + top-K returns + confusion patterns
    → change eligibility / factor thresholds in config or scoring
    → re-backfill (or re-scan) mega_runners
    → re-label / re-train
    → compare metrics
```

### What to look at

| Signal | Where | Tuning idea |
|--------|-------|-------------|
| Feature importance | Train logs / model artifact | Raise weight or tighten rules for high-importance factors (e.g. squeeze ratio) |
| High score, low forward return | Exported parquet / SQL | Raise Tier 2 floor (`LAUNCHPAD_TIER2_NORMALIZED_MIN`) or proximity band |
| Low recall (missed runners) | Compare mega_runners price peaks vs `filtered` rows | Soften eligibility (`LAUNCHPAD_PROXIMITY_*`, min volume) carefully |
| Horizon mismatch | Labels at 5/10/20/63 | Optimize rules for the horizon you trade (often **20d**) |
| Regime | `market_regime_multiplier` | Avoid promoting Tier 1 in weak regimes |

### Config knobs (code)

Most Launchpad thresholds live in `src/quant_hub/config.py` (`LAUNCHPAD_*`) and scoring in `src/quant_hub/scoring/launchpad.py`. After code changes:

```bash
cd /opt/stacks/quant-hub && docker compose up -d --build quant-hub
```

Then re-run backfill with `--no-resume` only for the dates you need to refresh (expensive) — or live-scan recent weeks and label those.

### Suggested success criteria before scaling to SP500

- Label status mostly `ok` for eligible rows  
- Clear separation: higher `final_score` / squeeze features → better h20 returns  
- Walk-forward AUC / top-K return better than score-only baseline  
- At least several thousand labeled **setup** rows (after leaving mega_runners)

Scale command pattern (same pipeline):

```bash
docker exec quant-hub quant-backfill launchpad --universe sp500_index --since 2021-07-29
docker exec quant-hub quant-ml warm-cache --universe sp500_index
docker exec quant-hub quant-ml label --strategy launchpad --universe sp500_index --since 2021-07-29
docker exec quant-hub quant-ml train --strategy launchpad --universe sp500_index --since 2021-07-29 --horizon 20
```

---

## 8. Current schedule (Launchpad + Lynch)

Authoritative file: `docker/crontab` (container TZ = America/New_York).

| When (ET) | Job |
|-----------|-----|
| Mon–Fri **5:10 PM** | `quant-launchpad-daily --universe sp500_index --no-email` |
| Mon–Fri **5:35 PM** | `quant-digest daily` (Launchpad tiers) |
| Sat **12:30 AM** (quarterly) | `quant-universe refresh sp500_index` |
| Sat **1:30 AM** | `quant-launchpad-all --cache --report both` |
| Sat **5:00 AM** | `quant-lynch-all --no-email` |
| Sat **6:00 AM** | `quant-ml label --strategy launchpad --universe sp500_index --since <90d>` |
| Sat **7:50 / 8:00 AM** | analytics + weekly Lynch digest |

For tuning, run Launchpad manually on `mega_runners` (see §3–§7). After editing crontab: `docker compose up -d --build quant-hub`.

---

## 9. Quick reference (copy-paste)

```bash
# 0) Sync universe
cp /opt/stacks/quant-hub/data/universes.json /mnt/fast/quant-data/data/universes.json
cp /opt/stacks/quant-hub/data/universes/mega_runners.txt /mnt/fast/quant-data/data/universes/mega_runners.txt

# 1) Live scan
docker exec quant-hub quant-launchpad --universe mega_runners --cache --report both

# 2) Backfill
docker exec quant-hub quant-backfill launchpad --universe mega_runners --since 2021-07-29

# 3) ML data
docker exec quant-hub quant-ml warm-cache --universe mega_runners
docker exec quant-hub quant-ml label --strategy launchpad --universe mega_runners --since 2021-07-29
docker exec quant-hub quant-ml export-features --strategy launchpad --universe mega_runners --since 2021-07-29 --horizon 20

# 4) Train
docker exec quant-hub quant-ml train --strategy launchpad --universe mega_runners --since 2021-07-29 --horizon 20
docker exec quant-hub quant-ml models --strategy launchpad --universe mega_runners
```

---

## 10. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Unknown universe 'mega_runners'` | Sync JSON + `.txt` to `/mnt/fast/quant-data/data/universes/` |
| Labels all `insufficient_future_bars` | Run `quant-ml warm-cache` first; recent scan dates need more future bars |
| Empty training set | Need backfill + labels; ensure Tier 1–3 rows exist (`setups_only`) |
| Export path missing | Check `/mnt/fast/quant-data/data/ml/features/` on the host volume |
| Code changes not visible in container | Rebuild: `docker compose up -d --build quant-hub` (or mount `PYTHONPATH` for one-offs) |
