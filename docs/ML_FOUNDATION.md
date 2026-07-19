# Launchpad ML Foundation

**Scope:** Launchpad only
**Detailed operator workflow:** [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md)
**Last updated:** 2026-07-19

## Purpose

Launchpad ML turns point-in-time technical scans into labeled training examples. It supports historical backfill, forward-return labels, feature exports, LightGBM training, and walk-forward evaluation. Live Launchpad scanning does not yet perform model inference.

```text
Point-in-time Launchpad scans
  → signal_outcomes forward-return labels
  → feature Parquet
  → registered model + evaluation
```

The initial operating path is `mega_runners`, then `sp500_index` after the workflow and data quality are validated.

## Data model

`signal_outcomes` is keyed by `(run_id, ticker, horizon_days)` and records:

- anchor date from scan provenance;
- forward return, maximum gain, and maximum drawdown;
- SPY return and excess return;
- binary return-threshold label;
- computation status.

`ml_models` records the model artifact, feature schema version, training dates, evaluation split, parameters, and metrics.

## Label definition

1. Anchor on the scan's `as_of_price` date, or its scan date if unavailable.
2. Enter at the first daily close strictly after the anchor.
3. Exit after the configured number of trading sessions.
4. Calculate path outcomes only within that forward window.
5. Compare to SPY over the same period.

Default horizons are 5, 10, 20, and 63 trading days. Labels are recomputable: later price data can change recent `insufficient_future_bars` rows to `ok`.

## Leakage controls

These are non-negotiable:

1. Export only values present in the Launchpad payload at scan time.
2. Never use a same-day or future price as the label entry.
3. Keep chronological train/test splits; do not randomly shuffle dates.
4. Purge or embargo overlapping per-ticker signals around label horizons.
5. Preserve the exact `run_id` lineage between signal, feature row, and label.
6. Exclude rows whose `label_status` is not `ok`.

## Operations

```bash
docker exec quant-hub quant-backfill launchpad --universe mega_runners --since 2021-07-29
docker exec quant-hub quant-ml warm-cache --universe mega_runners
docker exec quant-hub quant-ml label --strategy launchpad --universe mega_runners --since 2021-07-29
docker exec quant-hub quant-ml export-features --strategy launchpad --universe mega_runners --since 2021-07-29 --horizon 20
docker exec quant-hub quant-ml train --strategy launchpad --universe mega_runners --since 2021-07-29 --horizon 20
```

The Saturday scheduled label job covers recent Launchpad `sp500_index` history. Consult `docker/crontab` for the exact schedule.

## Retention

Do not truncate `scan_runs` or run destructive history cleanup on the ML database without a backup. Parent-run deletion cascades to ticker results and labels. Cache eviction is recoverable but can leave labels as `no_price` until the cache is rebuilt.

For commands, feature columns, training criteria, and troubleshooting, use [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) and [ML Ops](ML_OPS.md).
