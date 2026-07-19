# Launchpad ML Operations

**Scope:** Launchpad-first ML operations
**Detailed procedure:** [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md)
**Last updated:** 2026-07-19

## What runs

Launchpad ML uses historical point-in-time Launchpad scans to produce forward-return labels, feature Parquet, LightGBM artifacts, and walk-forward evaluation. It is an offline tuning workflow; live scans do not call a trained model.

| Step | Command family | Persistent result |
|---|---|---|
| Historical signals | `quant-backfill launchpad` | `scan_runs`, `ticker_results` |
| Price history | `quant-ml warm-cache` | daily Parquet cache |
| Labels | `quant-ml label --strategy launchpad` | `signal_outcomes` |
| Features | `quant-ml export-features --strategy launchpad` | Parquet |
| Train/evaluate | `quant-ml train` / `quant-ml evaluate` | artifact and `ml_models` |

## Standard workflow

Start with `mega_runners`:

```bash
docker exec quant-hub quant-launchpad --universe mega_runners --cache --report both
docker exec quant-hub quant-backfill launchpad --universe mega_runners --since 2021-07-29
docker exec quant-hub quant-ml warm-cache --universe mega_runners
docker exec quant-hub quant-ml label --strategy launchpad --universe mega_runners --since 2021-07-29
docker exec quant-hub quant-ml export-features --strategy launchpad --universe mega_runners --since 2021-07-29 --horizon 20
docker exec quant-hub quant-ml train --strategy launchpad --universe mega_runners --since 2021-07-29 --horizon 20
docker exec quant-hub quant-ml evaluate --model-id <id> --walk-forward
```

Use the full guide before scaling to `sp500_index`: [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md).

## Scheduled work

Cron labels recent Launchpad `sp500_index` scans at 6:00 AM ET every Saturday. The actual command and date range are defined by `docker/crontab`; do not duplicate or alter its schedule based on this guide.

## Verification

```bash
docker exec quant-hub quant-ml status
docker exec quant-hub quant-ml models --strategy launchpad
```

```sql
SELECT so.label_status, COUNT(*)
FROM signal_outcomes so
JOIN scan_runs sr ON sr.id = so.run_id
WHERE sr.strategy_id = 'launchpad'
GROUP BY so.label_status;
```

Only use `label_status = 'ok'` rows in training or result analysis.

## Troubleshooting

| Symptom | Resolution |
|---|---|
| `insufficient_future_bars` | Expected for recent scans; wait for bars or use a shorter horizon |
| `no_price` | Run `quant-ml warm-cache`, then label again |
| Empty training set | Confirm historical Launchpad runs, Tier 1–3 setup rows, and completed labels |
| Export absent | Check `/mnt/fast/quant-data/data/ml/features/launchpad/` |
| Metrics unstable | Increase sample size before making threshold changes; small `mega_runners` data validates plumbing, not production edge |

## Guardrails

- Back up Postgres before broad backfills.
- Do not truncate `scan_runs`; labels cascade with their parent runs.
- Keep training and evaluation chronological with purge/embargo controls.
- Tune thresholds offline, rerun scans/backfill, relabel, and compare holdout metrics.

See [ML Foundation](ML_FOUNDATION.md) for label semantics and leakage principles.
