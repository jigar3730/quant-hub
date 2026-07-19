# Quant Hub Data Model

**Scope:** Launchpad, Lynch, and Launchpad ML
**Schema source:** `src/quant_hub/infrastructure/postgres/schema.sql`
**Last updated:** 2026-07-19

## Data flow

```text
universes.json + ticker files
        │
        ├── Launchpad (daily OHLCV) ──┐
        └── Lynch (Yahoo fundamentals)├── scan_runs ── ticker_results
                                      │                    │
                                      │                    └── exports/dashboard/digests
                                      └── signal_outcomes ── ml_models
```

The scan key is `(scan_date, strategy_id, universe_id)`. Rerunning the same product, universe, and calendar day replaces the prior snapshot.

Current strategy IDs are `launchpad` and `lynch`.

## PostgreSQL

### `scan_runs`

Run-level summary:

| Column | Meaning |
|---|---|
| `id` | Surrogate primary key |
| `scan_date`, `scan_time` | Local scan date and persisted timestamp |
| `strategy_id`, `universe_id` | Product and named universe |
| `universe_size` | Symbols considered |
| `tier1_count`, `tier2_count`, `tier3_count`, `filtered_count` | Product-specific aggregate counts |
| `actionable_count` | Launchpad Tier 1/2 or Lynch passed count |
| `regime_label`, `regime_multiplier` | Launchpad market context; Lynch may use neutral/default context |
| `metadata` | JSONB provenance, filters, category counts, and quality summaries |

### `ticker_results`

One row per `(run_id, ticker)`:

| Column | Meaning |
|---|---|
| `eligible` | Passed the product gate |
| `tier` | Product-specific classification |
| `sector_etf` | Optional technical benchmark field |
| `final_score` | Product sort score |
| `filter_reason` | Exclusion reason |
| `detail` | Full product JSONB payload |

### `job_runs`

Operational audit records: job name, timings, status, ticker counts, and error message. It is not a foreign-key child of a scan run.

### `signal_outcomes`

Launchpad forward-return labels keyed by `(run_id, ticker, horizon_days)`.

| Field | Meaning |
|---|---|
| `anchor_date` | Point-in-time scan anchor |
| `forward_return_pct`, `excess_return_pct` | Stock return and return versus SPY |
| `forward_max_gain_pct`, `forward_max_drawdown_pct` | Path outcomes |
| `label_binary` | Configured return-threshold label |
| `label_status` | `ok`, `no_price`, `invalid_anchor`, or `insufficient_future_bars` |

### `ml_models`

Registry of Launchpad model artifacts: strategy, universe, horizon, feature schema version, parameters, metrics, feature columns, artifact path, training window, evaluation split, and status.

## Product payloads

### Launchpad `ticker_results.detail`

Launchpad writes eligibility, tier explanation, `summary`, and `scores`. The current score factors are:

- `squeeze_intensity`
- `tightness_percentile`
- `volume_vacuum_depth`
- `trend_proximity_match`
- `macd_zero_line` (Tier 1 ignition gate)

Useful values:

```text
summary.final_adjusted_score
summary.normalized_score
scores.<factor>.score
scores.<factor>.raw
eligibility.passed
eligibility.fail_reason
```

Launchpad scans stock-mode universes only; ETF-mode universes are skipped.

### Lynch `ticker_results.detail`

Lynch writes `passed`, `categories`, `lynch_score`, `checks`, `fundamental_snapshot`, `investor_summary`, and `metrics`.

Key fields include `pe_ratio`, `peg_ratio`, earnings growth, debt/equity, net cash, institutional ownership, analyst count, insider activity, shares change, revenue stability, and data-quality provenance.

`lynch_score` is the percentage of checks passed, not a weighted portfolio score. A null score indicates incomplete retrieval, not zero.

## Configuration, cache, and exports

| Layer | Location |
|---|---|
| Universe registry | `data/universes.json` |
| Live Docker data | `/mnt/fast/quant-data/data/` |
| Price cache | `/mnt/fast/quant-data/data/cache/prices/` |
| ML features/models | `/mnt/fast/quant-data/data/ml/` |
| Product exports | `/mnt/fast/quant-data/data/output/{launchpad,lynch}/` |
| Logs | `/mnt/fast/quant-data/logs/` |

Postgres is richer and canonical; exports are flattened convenience artifacts.

## Relationships and retention

`scan_runs` cascades to `ticker_results` and `signal_outcomes`. Deleting scan history therefore also destroys ML labels. Preserve historical Launchpad runs before data cleanup, and back up the database before broad backfills or maintenance.

Indexes cover scan date, ticker lookup, job start time, label status/run/anchor, and product/universe model lookup.

See [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) for feature and training details and [Lynch Scanner](LYNCH_SCANNER.md) for fundamental field semantics.
