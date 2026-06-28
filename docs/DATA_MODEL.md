# Quant Hub — Data Model Reference

**Version:** 1.0  
**Audience:** Developers, analysts, and operators  
**Last updated:** 2026-06-28

Related: [Breakout Scanner](BREAKOUT_SCANNER.md) · [Swing Scanner](SWING_SCANNER.md) · [Lynch Scanner](LYNCH_SCANNER.md) · [Runbook](RUNBOOK.md) · [Architecture Gaps](ARCHITECTURE_GAPS.md)

---

## Table of contents

1. [Overview](#1-overview)
2. [Entity-relationship diagram](#2-entity-relationship-diagram)
3. [Data flow](#3-data-flow)
4. [External inputs (Yahoo Finance)](#4-external-inputs-yahoo-finance)
5. [Configuration data](#5-configuration-data)
6. [Cache layer (files)](#6-cache-layer-files)
7. [PostgreSQL (system of record)](#7-postgresql-system-of-record)
8. [File exports](#8-file-exports)
9. [Strategy-specific ticker detail schemas](#9-strategy-specific-ticker-detail-schemas)
10. [Computed vs stored fields](#10-computed-vs-stored-fields)
11. [Indexes and retention](#11-indexes-and-retention)

---

## 1. Overview

Quant Hub data falls into five layers:

| Layer | Role | Location |
|-------|------|----------|
| **External** | Raw market data pulled at scan time | Yahoo Finance via `yfinance` |
| **Config** | Universe definitions, thresholds | `data/universes.json`, `src/quant_hub/config.py` |
| **Cache** | Reusable OHLCV + fundamentals snapshots | `data/cache/` (Parquet + JSON) |
| **System of record** | Latest scan results per day/strategy/universe | PostgreSQL `quant_hub` |
| **Exports** | CSV / JSON / Markdown for operators & dashboard | `data/output/{strategy}/{universe_id}/` |

**Primary key for scans:** `(scan_date, strategy_id, universe_id)` — rerunning the same day replaces the prior run.

**Strategies:** `breakout` (daily), `swing` (weekly), `lynch` (fundamental).

---

## 2. Entity-relationship diagram

```mermaid
erDiagram
    UNIVERSES_CONFIG ||--o{ UNIVERSE_TICKER_FILE : "file source"
    UNIVERSES_CONFIG ||--o{ SCAN_RUN : "universe_id"
    
    SCAN_RUN ||--|{ TICKER_RESULT : "run_id"
    SCAN_RUN {
        bigint id PK
        date scan_date
        timestamptz scan_time
        varchar strategy_id
        varchar universe_id
        int universe_size
        int tier1_count
        int tier2_count
        int tier3_count
        int filtered_count
        int actionable_count
        varchar regime_label
        float regime_multiplier
        jsonb metadata
    }
    
    TICKER_RESULT {
        bigint run_id PK_FK
        varchar ticker PK
        boolean eligible
        varchar tier
        varchar sector_etf
        float final_score
        text filter_reason
        jsonb detail
    }
    
    JOB_RUN {
        bigint id PK
        varchar job_name
        timestamptz started_at
        timestamptz finished_at
        varchar status
        int tickers_requested
        int tickers_fetched
        int tickers_failed
        text error_message
    }
    
    PARQUET_CACHE ||--o{ SCAN_RUN : "feeds OHLCV"
    FUNDAMENTALS_CACHE ||--o{ SCAN_RUN : "feeds breakout"
    YAHOO_FINANCE ||--o{ PARQUET_CACHE : "download"
    YAHOO_FINANCE ||--o{ FUNDAMENTALS_CACHE : "download"
    YAHOO_FINANCE ||--o{ LYNCH_METRICS : "pull"
    
    SCAN_RUN ||--o{ EXPORT_CSV : "writes"
    SCAN_RUN ||--o{ EXPORT_JSON : "writes"
    SCAN_RUN ||--o{ EXPORT_MD : "writes"
```

### Relationship summary

| From | To | Cardinality | Notes |
|------|-----|-------------|-------|
| `scan_runs` | `ticker_results` | 1:N | CASCADE delete; one row per ticker per run |
| `universes.json` | scan | logical | Defines ticker list; not a DB table |
| `job_runs` | scan | optional | Audit trail when `job_name` passed to CLI |
| Cache files | scan | N:1 | Many tickers → one scan run |

---

## 3. Data flow

```text
                    ┌─────────────────┐
                    │  universes.json │
                    │  + ticker files │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   ┌───────────┐      ┌───────────┐       ┌───────────┐
   │  Breakout │      │   Swing   │       │   Lynch   │
   │  (daily)  │      │  (weekly) │       │  (fund.)  │
   └─────┬─────┘      └─────┬─────┘       └─────┬─────┘
         │                  │                   │
         │ OHLCV 1d/2y      │ OHLCV 1wk/10y     │ yfinance .info
         │ + fundamentals   │                   │ + filings
         │ + SPY + sectors  │                   │
         ▼                  ▼                   ▼
   ┌─────────────────────────────────────────────────┐
   │              PostgreSQL                          │
   │  scan_runs  +  ticker_results.detail (JSONB)    │
   └────────────────────┬────────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
    CSV export    JSON report    Markdown summary
         │              │              │
         └──────────────┴──────────────┘
                        │
                        ▼
                 Streamlit dashboard
                 (loads from Postgres)
```

---

## 4. External inputs (Yahoo Finance)

All live data comes from **Yahoo Finance** through the `yfinance` Python library.

### Breakout inputs

| Data | API / method | Used for |
|------|--------------|----------|
| Daily OHLCV | `yf.download(ticker, start=…)` | Eligibility, 9 factor scores, regime (SPY) |
| Sector ETF OHLCV | Same download batch | RS vs sector |
| Quarterly income (via fundamentals module) | `Ticker.quarterly_income_stmt` | Revenue YoY, EPS combined |
| Ticker `.info` | `yf.Ticker(ticker).info` | Sector/industry → sector ETF map |

### Swing inputs

| Data | API | Used for |
|------|-----|----------|
| Weekly OHLCV | `yf.download(period=10y, interval=1wk)` | EMA20/50, RSI, ATR, MACD, setup rules |

### Lynch inputs

| Data | API | Used for |
|------|-----|----------|
| `.info` | Core fundamentals | P/E, PEG inputs, balance sheet, ownership |
| `.quarterly_income_stmt` | EPS/revenue series | 5Y CAGR, TTM growth, revenue CV |
| `.insider_purchases` | Insider buying 6M | Lynch checks |
| `.get_shares_full()` | Share count YoY | Lynch checks |

---

## 5. Configuration data

### `data/universes.json`

Registry of named universes. Not stored in Postgres.

| Field | Type | Description |
|-------|------|-------------|
| `universes.{id}.name` | string | Display name in dashboard |
| `universes.{id}.description` | string | Human description |
| `universes.{id}.eligibility_mode` | string | Optional: `stock` (default) or `etf` (relaxed breakout gates) |
| `universes.{id}.sources[]` | array | One or more sources merged & deduped |

**Source types:**

| type | Fields | Example |
|------|--------|---------|
| `file` | `path` → ticker list `.txt` | `data/universes/sp500.txt` |
| `screener` | `screener`, `count` | Yahoo most-actives, 250 symbols |

**Built-in universe IDs:** `sp500`, `large_cap_growth`, `small_cap_growth`, `mid_cap_growth`, `dividend_growers`, `fintech_growth`, `most_actives`, `sector_commodity_etfs`.

### Ticker list files (`data/universes/*.txt`)

One symbol per line; `#` comments allowed. Normalized to uppercase.

### Runtime thresholds (`src/quant_hub/config.py`)

| Constant | Value | Used by |
|----------|-------|---------|
| `MIN_TRADING_DAYS` | 200 | Breakout stock eligibility |
| `MIN_AVG_VOLUME` | 750,000 | Breakout stock liquidity |
| `MIN_PRICE` | $10 | Breakout stock minimum price |
| `ETF_MIN_TRADING_DAYS` | 120 | Breakout ETF eligibility |
| `ETF_MIN_AVG_VOLUME` | 500,000 | Breakout ETF liquidity |
| `ETF_MIN_PRICE` | $5 | Breakout ETF minimum price |
| `RAW_SCORE_MAX` | 120 | Breakout normalization reference |
| `LOOKBACK_DAYS` | 252 | 52-week range, price history |
| `SWING_MIN_BARS` | 60 | Minimum weekly bars |
| `BENCHMARK_TICKER` | SPY | Regime + RS market |

Sector mapping: `SECTOR_TO_ETF`, `INDUSTRY_TO_ETF` in `config.py` → `resolve_sector_etf()`.

---

## 6. Cache layer (files)

Host path (Docker): `/app/data/cache/` → bind mount `/mnt/fast/quant-data/data/cache/`.

### Daily price cache (breakout)

| Property | Value |
|----------|-------|
| Path | `data/cache/prices/1d/2y/{TICKER}.parquet` |
| TTL | 24 hours (file mtime) |
| Stale bar | > 5 calendar days on last bar |
| Columns | `Date`, `Open`, `High`, `Low`, `Close`, `Volume` |

### Weekly price cache (swing)

| Property | Value |
|----------|-------|
| Path | `data/cache/prices/1wk/10y/{TICKER}.parquet` |
| TTL | 7 days |
| Stale bar | > 10 calendar days |
| Note | Incomplete current week dropped if not Friday |

### Fundamentals cache (breakout)

| Property | Value |
|----------|-------|
| Path | `data/cache/fundamentals/{TICKER}.json` |
| TTL | 7 days |

**JSON fields (`FundamentalsSnapshot`):**

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | string | Symbol |
| `revenue_yoy` | float \| null | Blended revenue YoY growth (decimal, e.g. 0.25 = 25%) |
| `revenue_yoy_status` | string | `OK`, `MISSING`, `NOT_APPLICABLE`, `CAPPED`, `NEGATIVE` |
| `revenue_yoy_source` | string | e.g. TTM YoY, quarterly YoY |
| `eps_combined` | float \| null | Blended EPS growth metric for scoring |
| `eps_combined_status` | string | Same status enum |
| `eps_yoy` | float \| null | Raw YoY component |
| `eps_cagr_3y` | float \| null | 3-year CAGR component |
| `eps_source` | string | Derivation explanation |
| `quarters_available` | int | Filing depth used |
| `fetched_at` | ISO datetime | Cache timestamp |
| `fetch_error` | string \| null | Set on failure |

---

## 7. PostgreSQL (system of record)

**Database:** `quant_hub`  
**Schema:** `src/quant_hub/infrastructure/postgres/schema.sql`

### Table: `scan_runs`

One row per `(scan_date, strategy_id, universe_id)`.

| Column | Type | Generated by | Description |
|--------|------|--------------|-------------|
| `id` | BIGSERIAL PK | auto | Surrogate key; FK from `ticker_results` |
| `scan_date` | DATE | CLI / cron | Calendar date of scan (local today unless overridden) |
| `scan_time` | TIMESTAMPTZ | upsert time | UTC timestamp when persisted |
| `strategy_id` | VARCHAR(32) | service | `breakout`, `swing`, or `lynch` |
| `universe_id` | VARCHAR(64) | universe registry | e.g. `sp500`, `sector_commodity_etfs` |
| `universe_size` | INT | scan | Tickers in universe |
| `tier1_count` | INT | aggregated | Breakout: Tier 1; Swing: SETUP_LONG; Lynch: fast_grower |
| `tier2_count` | INT | aggregated | Breakout: Tier 2; Swing: SETUP_SHORT; Lynch: stalwart |
| `tier3_count` | INT | aggregated | Breakout: Tier 3; Lynch: asset_play; Swing: 0 |
| `filtered_count` | INT | aggregated | Failed eligibility / no setup / not passed |
| `actionable_count` | INT | aggregated | Breakout: T1+T2; Swing: setups; Lynch: passed |
| `regime_label` | VARCHAR(32) | SPY regime | `strong`, `neutral`, `weak`, `weekly`, `fundamental` |
| `regime_multiplier` | FLOAT | SPY regime | 1.0 / 0.85 / 0.6 (breakout); 1.0 (swing/lynch) |
| `metadata` | JSONB | `_build_scan_metadata()` | See below |

#### `scan_runs.metadata` JSONB

| Field | Strategies | Description |
|-------|------------|-------------|
| `schema_version` | all | Currently `1` |
| `market_regime` | all | Full regime object (see §9.1) |
| `filter_breakdown` | all | `{fail_reason: count}` |
| `eligible_count` | all | Tickers that passed hard gate |
| `excluded_count` | all | Tickers filtered out |
| `setup_long_count` | swing | SETUP_LONG count |
| `setup_short_count` | swing | SETUP_SHORT count |
| `fundamentals_quality` | breakout | EPS/revenue coverage stats |
| `preset` | lynch | CLI preset id |
| `preset_label` | lynch | Human preset name |
| `passed_count` | lynch | Lynch passed count |
| `category_counts` | lynch | `{fast_grower, stalwart, asset_play}` |
| `qualitative_overlay` | lynch | Manual review checklist text |
| `metrics_quality` | lynch | Fetch success / complete profile stats |
| `data_provenance` | all | Lineage block (see §9.4) |

### Table: `ticker_results`

One row per ticker per scan run.

| Column | Type | Generated by | Description |
|--------|------|--------------|-------------|
| `run_id` | BIGINT PK,FK | `scan_runs.id` | Parent scan |
| `ticker` | VARCHAR(16) PK | universe | Symbol |
| `eligible` | BOOLEAN | strategy gate | Passed eligibility / setup / Lynch screen |
| `tier` | VARCHAR(32) | assign tier | Strategy-specific tier label |
| `sector_etf` | VARCHAR(16) | sector map | Benchmark ETF (breakout stocks; SPY for ETF universe) |
| `final_score` | FLOAT | scoring | Primary sort score (see strategy) |
| `filter_reason` | TEXT | eligibility | Fail code when not eligible |
| `detail` | JSONB | full ticker report | **Complete per-ticker object** — see §9 |

### Table: `job_runs`

Optional audit log when scans run with `job_name`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | BIGSERIAL PK | Job id |
| `job_name` | VARCHAR(128) | e.g. `breakout-sp500-daily`, `swing-weekly` |
| `started_at` | TIMESTAMPTZ | Job start |
| `finished_at` | TIMESTAMPTZ | Job end |
| `status` | VARCHAR(16) | `success` or `failed` |
| `tickers_requested` | INT | Universe size |
| `tickers_fetched` | INT | Successfully processed |
| `tickers_failed` | INT | Fetch/compute failures |
| `error_message` | TEXT | Failure detail |

---

## 8. File exports

Path pattern: `data/output/{strategy_id}/{universe_id}/`

| Strategy | CSV | JSON | Markdown |
|----------|-----|------|----------|
| breakout | `scan_results.csv` | `report.json` | `summary.md` |
| swing | `setups.csv` | — | — |
| lynch | `scan_results.csv` | `report.json` | `summary.md` |

**Legacy sp500 copies:** `data/output/breakout_scan_*`, `lynch_scan_*` (backward compatible).

### Breakout CSV columns

| Column | Source |
|--------|--------|
| `ticker` | symbol |
| `eligible` | boolean |
| `filter_reason` | fail code |
| `raw_score` | sum of factor scores |
| `normalized_score` | 0–100 (dynamic max for ETF mode) |
| `regime_multiplier` | SPY regime |
| `final_adjusted_score` | normalized × multiplier |
| `tier` | Tier 1/2/3/filtered |
| `sector_etf` | mapped ETF |
| `{factor}_score` | rs_market, rs_sector, accumulation, relative_volume, compression, pattern, resistance, revenue, eps |

### Swing CSV columns (`setups.csv`)

Confirmed setups only: `Symbol`, `Setup Type`, `Close`, `EMA20`, `EMA50`, `RSI`, `ATR`, `Notes`.

Full universe lives in Postgres only (not setups CSV).

### Lynch CSV columns

Flattened subset: ticker, passed, categories, lynch_score, P/E, PEG, growth, etc. (via `_csv_row()`).

### JSON report top-level (`report.json`)

| Field | Description |
|-------|-------------|
| `strategy_id` | `breakout` or `lynch` |
| `scan_summary` | Aggregates (mirrors `scan_runs` + strategy extras) |
| `market_regime` | Regime object |
| `tickers[]` | Full per-ticker detail array (same shape as Postgres `detail`) |
| `candidates[]` | Lynch only: passed names sorted |
| `data_provenance` | Lineage metadata |

---

## 9. Strategy-specific ticker detail schemas

The `ticker_results.detail` JSONB column stores the **full ticker report** from each strategy. The dashboard reads this blob directly.

### 9.1 Shared: `market_regime` (breakout / in metadata)

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | `strong`, `neutral`, `weak` |
| `multiplier` | float | Score weight |
| `meaning` | string | Human explanation |
| `spy_price` | float | Latest SPY close |
| `sma50` | float | SPY 50-day SMA |
| `sma200` | float | SPY 200-day SMA |
| `return_63d_pct` | float | SPY 63-day return % |
| `pct_below_52w_high` | float | Distance from 52w high |
| `high_52w` | float | SPY 52-week high |

### 9.2 Breakout `detail` (per ticker)

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | string | Symbol |
| `verdict` | string | `eligible` or `excluded` |
| `eligible` | boolean | Passed eligibility |
| `tier` | string | Tier 1 / Tier 2 / Tier 3 / filtered |
| `tier_reason` | string | Human tier explanation |
| `sector_etf` | string | RS sector benchmark |
| `summary.raw_score` | float | Sum of factor scores |
| `summary.normalized_score` | float | 0–100 |
| `summary.regime_multiplier` | float | From SPY regime |
| `summary.final_adjusted_score` | float | normalized × multiplier |
| `eligibility.passed` | boolean | Gate result |
| `eligibility.fail_reason` | string | e.g. `trend_misaligned` |
| `eligibility.checks[]` | array | Each: `rule`, `passed`, `value`, `threshold` |
| `scores.{factor}` | object | Per-factor: `score`, `max`, `raw`, `meaning` |
| `fundamentals` | object | Cached revenue/EPS snapshot |

**Breakout factor keys in `scores`:** `rs_market`, `rs_sector`, `accumulation`, `relative_volume`, `compression`, `pattern`, `resistance`, `revenue`, `eps` (revenue/eps omitted for ETF mode).

### 9.3 Swing `detail` (per ticker)

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | string | Symbol |
| `eligible` | boolean | Has confirmed setup |
| `tier` | string | `SETUP_LONG`, `SETUP_SHORT`, or `filtered` |
| `tier_reason` | string | Setup note or fail summary |
| `summary.swing_score` | float | Quality score 0–100 |
| `summary.final_adjusted_score` | float | Same as swing_score |
| `summary.rsi` | float | Latest weekly RSI |
| `setup_detail.close` | float | Latest weekly close |
| `setup_detail.ema20` | float | 20-week EMA |
| `setup_detail.ema50` | float | 50-week EMA |
| `setup_detail.rsi` | float | 14-period RSI (weekly) |
| `setup_detail.atr` | float | 14-period ATR (weekly) |
| `setup_detail.macd_hist` | float | MACD histogram |
| `setup_detail.macd_hist_prev` | float | Prior week MACD hist |
| `setup_detail.bars_evaluated` | int | Weekly bars after warm-up |
| `setup_detail.checks_passed` | int | Hard rules passed (0–5) |
| `setup_detail.checks_total` | int | Always 5 on scored side |
| `setup_detail.swing_score` | float | Final quality score |
| `setup_detail.base_score` | float | Partial credit sum |
| `setup_detail.penalty_total` | float | Negative sum (≤ −25 cap) |
| `setup_detail.quality_label` | string | A / B / C / D band |
| `setup_detail.scored_side` | string | `long` or `short` |
| `setup_detail.rule_breakdown[]` | array | Per-rule partial credit |
| `setup_detail.penalties[]` | array | `{code, label, amount, reason}` |
| `swing_checks[]` | array | All 10 long+short hard checks |
| `eligibility.passed` | boolean | Setup gate |
| `eligibility.fail_reason` | string | e.g. `no_setup`, `insufficient_data` |
| `scores` | object | Mix of rule scores + indicator levels |

### 9.4 Lynch `detail` (per ticker)

| Field | Type | Description |
|-------|------|-------------|
| `ticker` | string | Symbol |
| `company_name` | string | From Yahoo |
| `sector` | string | Yahoo sector |
| `passed` | boolean | Lynch screen gate |
| `eligible` | boolean | Same as passed |
| `preset` | string | Scan preset id |
| `categories[]` | string[] | `fast_grower`, `stalwart`, `asset_play` |
| `lynch_score` | float \| null | % checks passed; null if fetch failed |
| `tier` | string | Primary category or `filtered` |
| `tier_reason` | string | Pass/fail explanation |
| `fail_reason` | string | First failed rule |
| `investor_summary` | string | Plain-English paragraph |
| `fundamental_snapshot[]` | array | Curated display rows |
| `checks[]` | array | Enriched quantitative checks |
| `metrics` | object | **Full raw metrics blob** — see Lynch doc |
| `pe_ratio`, `peg_ratio`, … | float | Top-level copies for tables/email |
| `summary.final_adjusted_score` | float | = lynch_score |

**Key fields inside `metrics` (Lynch raw):** `pe_ratio`, `peg_ratio`, `eps_growth_5y`, `eps_growth_ttm`, `eps_growth_for_peg`, `debt_to_equity`, `net_cash`, `institutional_ownership`, `analyst_count`, `insider_purchases_6m`, `shares_outstanding_change_yoy`, `revenue_cv`, `return_on_equity`, `dividend_yield`, `price_to_book`, `data_quality`, `fetched_at`, source fields.

### 9.5 `data_provenance` (lineage)

Attached to JSON reports and `scan_runs.metadata`.

| Field | Description |
|-------|-------------|
| `scan_date` | ISO date |
| `scan_time_utc` | ISO UTC timestamp |
| `universe_id` | Universe key |
| `strategy_id` | Strategy key |
| `price_source` | `yfinance` |
| `price_cache` | `parquet` or `live` |
| `fundamentals_cache` | `parquet` or `live` (breakout) |
| `as_of_price` | Last bar date in price data |
| `interval`, `period`, `dry_run` | Optional extras |

---

## 10. Computed vs stored fields

| Data | Computed at scan? | Stored in Postgres? | Stored on disk? |
|------|-------------------|---------------------|-----------------|
| Yahoo OHLCV | Pulled | No (cache only) | Parquet cache |
| Yahoo fundamentals (breakout) | Pulled + derived | Inside `detail` (breakout) | JSON cache |
| Lynch metrics | Pulled + derived | Inside `detail.metrics` | JSON export |
| Eligibility checks | Yes | `detail.eligibility` | JSON export |
| Breakout 9 factors | Yes | `detail.scores` + CSV columns | CSV/JSON |
| Regime multiplier | Yes (SPY) | `scan_runs` + metadata | JSON |
| Swing indicators | Yes | `detail.setup_detail` | Postgres only |
| Swing quality score | Yes | `detail.setup_detail.swing_score` | Postgres |
| Lynch lynch_score | Yes | `detail.lynch_score` | CSV/JSON |
| Tier assignment | Yes | `ticker_results.tier` | CSV/JSON |
| Email HTML | Yes | No | No |
| Dashboard tables | No | Read from Postgres | — |

**Important:** Postgres `detail` is the **richest** copy. CSV files are flattened subsets. Swing full universe exists only in Postgres.

---

## 11. Indexes and retention

### Indexes

| Index | Table | Columns |
|-------|-------|---------|
| PK | `scan_runs` | `(scan_date, strategy_id, universe_id)` UNIQUE |
| PK | `ticker_results` | `(run_id, ticker)` |
| `idx_scan_runs_date` | `scan_runs` | `scan_date DESC` |
| `idx_job_runs_started` | `job_runs` | `started_at DESC` |

### Retention

| Operation | Behavior |
|-----------|----------|
| Same-day rescan | Upsert replaces `scan_runs` row; deletes & reinserts `ticker_results` for that run |
| `scripts/full-rescan.sh` | `TRUNCATE scan_runs CASCADE` — wipes all history |
| Cache TTL | Prices/fundamentals expire by file age; refetched on next scan |
| Fixture cleanup | `quant-hub cleanup-fixtures` removes test universe rows |

### Docker volumes

| Host path | Container | Contents |
|-----------|-----------|----------|
| `/mnt/fast/quant-data/postgres` | `/var/lib/postgresql/data` | PostgreSQL files |
| `/mnt/fast/quant-data/data` | `/app/data` | cache, output, universes |
| `/mnt/fast/quant-data/logs` | `/app/logs` | cron.log, scan.log |

---

## Quick reference: score fields by strategy

| Strategy | Primary score column | Range | Meaning |
|----------|---------------------|-------|---------|
| Breakout | `final_adjusted_score` | 0–100+ | Normalized factor sum × regime |
| Swing | `setup_detail.swing_score` | 0–100 | Partial rule credit − penalties |
| Lynch | `lynch_score` | 0–100 or null | % quantitative checks passed |

| Strategy | Actionable definition |
|----------|----------------------|
| Breakout | Tier 1 + Tier 2 |
| Swing | SETUP_LONG + SETUP_SHORT |
| Lynch | `passed = true` |

---

## Related source files

| Topic | Path |
|-------|------|
| Postgres schema | `src/quant_hub/infrastructure/postgres/schema.sql` |
| Repository / upsert | `src/quant_hub/infrastructure/postgres/repository.py` |
| Breakout report builder | `src/quant_hub/report/builder.py` |
| Factor diagnostics | `src/quant_hub/report/diagnostics.py` |
| Swing serialization | `src/quant_hub/strategies/swing/scanner.py` → `analysis_to_report()` |
| Lynch evaluation | `src/quant_hub/lynch/runner.py` → `_evaluate()` |
| Fundamentals types | `src/quant_hub/data/fundamentals/types.py` |
| Parquet cache | `src/quant_hub/infrastructure/cache/parquet_cache.py` |
| Provenance | `src/quant_hub/data/provenance.py` |
