# Lynch Scanner — Data Pipeline Reference

**Version:** 1.0  
**Audience:** Analysts and operators who want to understand how Lynch fundamentals are pulled, calculated, and stored  
**Last updated:** 2026-06-28

Related docs: [User Manual](USER_MANUAL.md) · [Runbook](RUNBOOK.md) · [Launchpad Scanner](LAUNCHPAD_SCANNER.md) · [Digest Policy](DIGEST_POLICY.md)

---

## Table of contents

1. [Pipeline overview](#1-pipeline-overview)
2. [Data pull (Yahoo Finance)](#2-data-pull-yahoo-finance)
3. [Raw metrics](#3-raw-metrics)
4. [Evaluation logic](#4-evaluation-logic)
5. [Lynch score and quantitative checks](#5-lynch-score-and-quantitative-checks)
6. [Key fundamentals (dashboard)](#6-key-fundamentals-dashboard)
7. [Plain-English summary](#7-plain-english-summary)
8. [Storage](#8-storage)
9. [Dashboard sections mapped to data](#9-dashboard-sections-mapped-to-data)
10. [Pass vs score vs categories](#10-pass-vs-score-vs-categories)
11. [Configuration and source code](#11-configuration-and-source-code)

---

## 1. Pipeline overview

```text
Universe tickers
    → fetch_lynch_metrics_batch()     [lynch/metrics.py]
    → Raw metrics dict per ticker
    → _evaluate()                       [lynch/runner.py]
        → Anti-filters
        → Preset / base screen / categories
        → lynch_score + enrich_checks
        → investor_summary + fundamental_snapshot
    → Postgres + CSV + JSON + dashboard
```

**Entry point:** `quant-lynch` / `quant-lynch-all` → `LynchScanService.run()` → `LynchScannerRunner.run()` in `src/quant_hub/lynch/runner.py`.

**Schedule:** Saturday **5:00 AM ET** — `quant-lynch-all --no-email` on all stock universes (`lynch_enabled: true`; ETFs skipped). Weekly digest still highlights **`sp500_index`** Lynch results.

Each scan processes every ticker in the selected universe. Results for the same `(scan_date, lynch, universe_id)` replace the previous run (upsert).

---

## 2. Data pull (Yahoo Finance)

**Module:** `src/quant_hub/lynch/metrics.py`

For each ticker the scanner calls **yfinance** (`yf.Ticker(ticker)`):

| Pull | Purpose |
|------|---------|
| `.info` | P/E, forward P/E, market cap, debt, ROE, institutional ownership, analyst count, dividend yield, P/B, etc. |
| `.quarterly_income_stmt` | EPS series for 5-year CAGR and TTM growth; revenue for stability |
| `.insider_purchases` | Insider buying in the last 6 months |
| `.get_shares_full()` | Share count change year-over-year |
| Revenue rows | **Revenue coefficient of variation** (stability) |

### Batching and reliability

`fetch_lynch_metrics_batch()` fetches tickers in parallel batches with retries and backoff to reduce Yahoo rate-limit failures. Tunables in `src/quant_hub/config.py`:

- `LYNCH_FETCH_WORKERS`
- `LYNCH_FETCH_BATCH_SIZE`
- `LYNCH_FETCH_BATCH_DELAY_SEC`
- `LYNCH_FETCH_RETRIES`
- `LYNCH_FETCH_RETRY_BASE_SEC`

If a fetch fails after retries, the ticker returns `{"ticker": "...", "error": "fetch_failed"}`. The dashboard shows **—** for Lynch score on those rows (`lynch_score: null`), not a fake zero.

### Normalization

Growth rates, debt/equity, dividend yield, and similar fields pass through helpers in `src/quant_hub/data/quality.py` so Yahoo’s mixed formats (decimal vs percent) are consistent before checks run.

---

## 3. Raw metrics

The **`metrics`** dict is the full fundamentals blob attached to each ticker result. It is stored in Postgres and shown in the dashboard **Raw metrics** expander on **Ticker Detail**.

### Core computed fields

| Field | Source / calculation |
|-------|----------------------|
| `pe_ratio` | Trailing P/E when available; else forward P/E |
| `peg_ratio` | **Computed:** `P/E ÷ earnings growth (%)`, capped at 5.0; falls back to Yahoo `pegRatio` when growth is missing |
| `eps_growth_5y` | 5-year EPS CAGR from quarterly filings, else Yahoo `earningsGrowth` |
| `eps_growth_ttm` | TTM EPS vs prior four quarters, else Yahoo `earningsQuarterlyGrowth` |
| `eps_growth_for_peg` | **Prefers TTM** over 5Y for PEG (more current) |
| `debt_to_equity`, `net_cash` | Yahoo balance-sheet fields (normalized) |
| `institutional_ownership`, `analyst_count` | Yahoo |
| `insider_purchases_6m`, `shares_outstanding_change_yoy` | Yahoo tables |
| `revenue_cv` | Std / mean of recent quarterly revenue (lower = steadier) |
| `return_on_equity`, `dividend_yield`, `price_to_book`, … | Yahoo |
| `data_quality.complete`, `data_quality.missing_fields` | Whether enough fields exist to run checks confidently |

### PEG calculation

```python
# src/quant_hub/lynch/metrics.py — compute_peg()
peg = pe / growth_pct   # growth_pct from growth_to_percent(); result capped at 5.0
```

Growth for PEG uses `eps_growth_for_peg` (TTM preferred, then 5Y).

### Provenance fields

The metrics dict also records how values were derived, for debugging and the data-quality banner:

- `pe_source`, `peg_source`, `eps_growth_source`, `eps_growth_explanation`
- `fetched_at`

Scan-level quality summary: `lynch_metrics_quality_summary()` → `scan_summary.metrics_quality` (fetch success %, complete profiles %, missing PEG count, etc.).

---

## 4. Evaluation logic

**Module:** `src/quant_hub/lynch/runner.py` → `_evaluate()`

Evaluation runs in order for each ticker.

### Step A — Anti-filters (required first)

**Module:** `src/quant_hub/lynch/filters.py` → `apply_anti_filters()`

| Check | Rule |
|-------|------|
| `positive_earnings` | Trailing EPS > 0 |
| `return_on_equity` | ROE ≥ 8% |
| `revenue_stability` | Revenue CV ≤ 0.75 (missing CV = pass) |

If any anti-filter fails, evaluation stops with a `fail_reason` (e.g. `no_earnings`, `return_on_equity`). Category and base checks are not run.

### Step B — Preset / screen

**Thresholds:** `src/quant_hub/lynch/config.py`  
**CLI:** `--preset` (default `summary`)

| Preset | Behavior |
|--------|----------|
| **`summary`** (default) | Run base screen + assign categories; **pass** if base passes **or** any category matches |
| **`base`** | `apply_base_screen()` only — all base checks must pass |
| **`fast_grower`** | Fast-grower category classifier only |
| **`stalwart`** | Stalwart category classifier only |
| **`asset_play`** | Asset-play category classifier only |

#### Base screen checks (`apply_base_screen()`)

| Check | Threshold |
|-------|-----------|
| PEG | ≤ 1.2 |
| EPS growth | 10% – 50% (uses `eps_growth_for_peg` / 5Y) |
| P/E | 0 < P/E < 25 |
| Financial strength | D/E < 50% **or** net cash > 0 |
| Wall Street neglect | Institutional ownership < 65% **or** ≤ 8 analysts (requires data; missing = fail) |
| Insider alignment | Insider buying > 0 **or** shares outstanding declining YoY (requires data; missing = fail) |

#### Categories (`src/quant_hub/lynch/categories.py`)

A ticker can match zero, one, or several categories:

| Category | Highlights |
|----------|------------|
| **Fast grower** | Market cap < $10B, EPS growth ≥ 15%, PEG ≤ 1.2, D/E < 40% |
| **Stalwart** | Market cap ≥ $10B, EPS growth 8–18%, P/E ≤ 22, dividend yield ≥ 1.2% |
| **Asset play** | P/B ≤ 1.0, net cash ≥ 30% of share price |

With preset **`summary`**, a name can **pass** on a category alone even when the base screen fails.

---

## 5. Lynch score and quantitative checks

**Module:** `src/quant_hub/lynch/filters.py` → `lynch_score()`

```python
lynch_score = round(passed_checks / total_checks * 100, 1)
```

This is **not** a weighted model. It is the **percentage of checks that passed** among all checks executed for that ticker (anti-filters plus base and/or category checks).

Each check is enriched in `src/quant_hub/lynch/explain.py` → `enrich_checks()` with:

| Field | Meaning |
|-------|---------|
| `label` | Human-readable name (e.g. “PEG ratio (price vs growth)”) |
| `why_it_matters` | Lynch-style rationale |
| `plain_value` | Formatted metric value |
| `result_text` | Pass/fail sentence for the dashboard |

The enriched list is what the dashboard shows as **Quantitative checks** on **Ticker Detail**.

---

## 6. Key fundamentals (dashboard)

**Module:** `src/quant_hub/lynch/explain.py` → `build_fundamental_snapshot()`

**Key fundamentals** is a curated subset of `metrics` for display — not a separate API call. Each row includes:

- `label`, `display`, `explanation`, `source` (e.g. “Yahoo Finance”, “quarterly income statement”)

Typical rows: P/E, PEG, earnings growth used for PEG, 5Y EPS CAGR, debt/equity, net cash, market cap, P/B, institutional ownership.

---

## 7. Plain-English summary

**Module:** `src/quant_hub/lynch/explain.py` → `build_investor_summary()`

One paragraph built from metrics, pass/fail status, and categories. Shown as **In plain English** on **Ticker Detail**.

---

## 8. Storage

### PostgreSQL (system of record)

**Module:** `src/quant_hub/infrastructure/postgres/repository.py` → `ScanRepository.upsert_scan()`

| Table | Lynch content |
|-------|---------------|
| **`scan_runs`** | One row per `(scan_date, strategy_id='lynch', universe_id)`: tier counts (mapped from category counts), actionable count, preset, category counts, `metrics_quality` in `metadata` JSON |
| **`ticker_results`** | One row per ticker; full ticker object in **`detail` JSONB** |

Indexed columns on `ticker_results`: `eligible`, `tier`, `final_score` (= Lynch score), `filter_reason`.

#### Per-ticker `detail` JSON (representative shape)

```json
{
  "ticker": "XYZ",
  "company_name": "...",
  "sector": "...",
  "passed": true,
  "categories": ["fast_grower"],
  "lynch_score": 85.7,
  "pe_ratio": 18.2,
  "peg_ratio": 0.9,
  "metrics": { "...": "full raw blob" },
  "checks": [ "... enriched quantitative checks ..." ],
  "fundamental_snapshot": [ "... key fundamentals rows ..." ],
  "investor_summary": "...",
  "tier_reason": "...",
  "fail_reason": null,
  "summary": { "final_adjusted_score": 85.7 },
  "eligibility": { "passed": true, "fail_reason": null }
}
```

The dashboard loads scans via `ScanRepository.load_report()`, which rebuilds the `tickers` list from `ticker_results.detail`.

**History:** `ScanRepository.lynch_ticker_history()` tracks `lynch_score`, `passed`, `peg_ratio`, and `categories` across past runs for score-history charts.

### File exports

| Output | Path |
|--------|------|
| CSV (flattened columns) | `data/output/lynch/{universe_id}/scan_results.csv` |
| JSON (full report) | `data/output/lynch/{universe_id}/report.json` |
| Markdown summary | `data/output/lynch/{universe_id}/summary.md` |
| Legacy (sp500 only) | `data/output/lynch_scan_report.json`, etc. |

CSV is a **flattened** subset via `_csv_row()` in `runner.py` — not the full checks/metrics JSON.

### Same-day reruns

Re-running `quant-lynch` on the same calendar day for the same universe **replaces** the previous run (`ON CONFLICT` upsert on `scan_runs`, then delete/reinsert `ticker_results` for that run).

---

## 9. Dashboard sections mapped to data

| UI section | Source field | What it is |
|------------|--------------|------------|
| **Key fundamentals** | `fundamental_snapshot` | Curated, explained subset for analysts |
| **Quantitative checks** | `checks` (after `enrich_checks`) | Pass/fail rules with plain-English sentences |
| **Raw metrics** | `metrics` | Complete Yahoo-derived + computed field bag |

All three are built **during the scan** in `_evaluate()` and stored together in Postgres `detail`.

**Dashboard module:** `viz/lynch_components.py` (Candidates, Overview, All Tickers, Ticker Detail tabs).

---

## 10. Pass vs score vs categories

| Field | Meaning |
|-------|---------|
| **`passed`** | Boolean gate from preset logic (e.g. `summary` = base **or** any category) |
| **`lynch_score`** | % of checks passed — can be high even when `passed=false`, or low when many checks ran |
| **`categories`** | Tags: `fast_grower`, `stalwart`, `asset_play` |
| **`lynch_score: null`** | Fetch failed — show **—**, not zero |
| **`fail_reason`** | First failed anti-filter or screen rule (when not passed) |

---

## 11. Configuration and source code

| Topic | Location |
|-------|----------|
| Thresholds (PEG, P/E, growth bands, category rules) | `src/quant_hub/lynch/config.py` |
| Yahoo fetch + metrics dict | `src/quant_hub/lynch/metrics.py` |
| Anti-filters, base screen, Lynch score | `src/quant_hub/lynch/filters.py` |
| Category classifiers | `src/quant_hub/lynch/categories.py` |
| Explanations and snapshots | `src/quant_hub/lynch/explain.py` |
| Scan orchestration + CSV/report export | `src/quant_hub/lynch/runner.py` |
| Application service + CLI wiring | `src/quant_hub/application/lynch_service.py`, `src/quant_hub/cli/lynch_all.py` |
| Postgres persistence | `src/quant_hub/infrastructure/postgres/repository.py` |
| Data quality summaries | `src/quant_hub/data/quality.py` |

### Default threshold reference

| Constant | Value |
|----------|-------|
| `PEG_MAX` | 1.2 |
| `EPS_GROWTH_MIN` / `MAX` | 10% / 50% |
| `PE_MAX` | 25 |
| `DEBT_TO_EQUITY_MAX` | 50% |
| `INSTITUTIONAL_OWNERSHIP_MAX` | 65% |
| `ANALYST_COVERAGE_MAX` | 8 |
| `ROE_MIN_ANTI` | 8% |
| `REVENUE_CV_MAX` | 0.75 |

See `config.py` for fast-grower, stalwart, and asset-play category thresholds.
