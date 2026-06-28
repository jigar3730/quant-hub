# Breakout Scanner — Data Pipeline Reference

**Version:** 1.0  
**Audience:** Analysts and operators who want to understand how daily breakout data is pulled, calculated, scored, tiered, and stored — and how to read the dashboard  
**Last updated:** 2026-06-28

Related docs: [User Manual](USER_MANUAL.md) · [Runbook](RUNBOOK.md) · [Swing Scanner](SWING_SCANNER.md) · [Lynch Scanner](LYNCH_SCANNER.md)

---

## Table of contents

1. [Pipeline overview](#1-pipeline-overview)
2. [Schedule](#2-schedule)
3. [Three layers: eligibility, score, tier](#3-three-layers-eligibility-score-tier)
4. [Data pull](#4-data-pull)
5. [Eligibility filters (hard gate)](#5-eligibility-filters-hard-gate)
6. [Market regime](#6-market-regime)
7. [Score components (9 factors)](#7-score-components-9-factors)
8. [Aggregate scoring](#8-aggregate-scoring)
9. [Tier assignment](#9-tier-assignment)
10. [How to read the dashboard](#10-how-to-read-the-dashboard)
11. [Storage](#11-storage)
12. [Configuration and source code](#12-configuration-and-source-code)

---

## 1. Pipeline overview

```text
Universe tickers
    → download_prices() + download_fundamentals()   [yfinance + parquet cache]
    → ScanContext (SPY, sector ETFs, regime)
    → StrategyEngine.run()                          [engine/runner.py]
        → BreakoutEligibilityFilter                 per ticker
        → 9 factor scores (universe + ticker pass)
        → aggregate_breakout_ticker()               raw / normalized / final
        → assign_tier()                             Tier 1 / 2 / 3 / filtered
    → build_scan_report()                           rich per-ticker JSON
    → Postgres + CSV + JSON + MD + optional email
```

**Entry points:**

| Command | Service | Typical use |
|---------|---------|-------------|
| `quant-daily --universe sp500` | `ScanService` | Scheduled daily job (cache on, email on, reports JSON+MD) |
| `quant-scan --universe sp500 --cache` | `ScanService` | Manual scan, no email by default |
| `quant-scan-all --cache --email` | `ScanService` | All universes in `universes.json` |

**Strategy spec:** `src/quant_hub/strategies/breakout/spec.py` → `BREAKOUT_STRATEGY`.

**Cadence:** **Daily** bars (`1d`), ~**2 years** of price history (252 trading-day lookback; see [Data pull](#4-data-pull)).

Every ticker in the universe gets a row. Ineligible names are **`filtered`** with zero scores and a fail reason.

---

## 2. Schedule

| When | Command | Universe |
|------|---------|----------|
| **Mon–Fri, 5:17 PM ET** | `quant-daily --universe sp500` | `sp500` only |

Defined in `docker/crontab`. Other universes are **manual** unless you add cron lines.

Re-running on the **same calendar day** for the same universe **replaces** that day’s scan (Postgres upsert).

---

## 3. Three layers: eligibility, score, tier

| Layer | Field(s) | Meaning |
|-------|----------|---------|
| **1. Eligibility** | `eligible`, `eligibility.fail_reason` | **Hard gate.** Must pass all trend/liquidity/52-week checks before any factor scoring. Fail → `tier = filtered`, scores = 0. |
| **2. Score** | `summary.raw_score`, `normalized_score`, `final_adjusted_score` | **Continuous 0–100 scale** (after normalization × regime). Sum of 9 factor components. |
| **3. Tier** | `tier` | **Conviction bucket** for eligible names only: Tier 1 / Tier 2 / Tier 3. |

### Actionable vs watchlist

| Label | Definition |
|-------|------------|
| **Actionable** | Tier 1 + Tier 2 (`scan_summary.actionable_count`) |
| **Tier 1** | Highest conviction — strict multi-factor bar (see [Tier assignment](#9-tier-assignment)) |
| **Tier 2** | Watchlist — normalized score ≥ 65 |
| **Tier 3** | Eligible but below watchlist threshold (normalized < 65) |
| **filtered** | Failed eligibility or no price data |

### Examples

| Situation | Eligible? | Tier | How to read |
|-----------|-----------|------|-------------|
| Strong RS, compression, volume | yes | Tier 1 | Email + Actionable Watchlist; top sort key |
| Good score, weak compression | yes | Tier 2 | Watchlist; `tier_reason` explains missing Tier 1 criteria |
| Passes trend filters, low RS | yes | Tier 3 | Scored but not actionable |
| Price below SMA200 stack | no | filtered | See eligibility checks — no component scores |
| Norm 82, final 68 in weak regime | yes | Tier 2 | Regime multiplier blocked Tier 1 (`final` < 70) |

**Sort key:** `final_adjusted_score` (desc), then `rs_market_score`, then `accumulation_score`.

---

## 4. Data pull

### Daily prices

**Module:** `src/quant_hub/infrastructure/market/yfinance_prices.py`

| Setting | Value | Config |
|---------|-------|--------|
| Bar size | Daily | `1d` |
| Lookback | ~252 trading days | `LOOKBACK_DAYS = 252` |
| Fetch window | ~403 calendar days | `lookback_days × 1.6` |
| Source | Yahoo via `yfinance` | `auto_adjust=True` |
| Cache | Parquet per ticker | `data/cache/prices/1d/2y/` |
| Cache TTL | 24 hours | `CACHE_TTL_HOURS` |
| Stale bar threshold | 5 days | `max_bar_age_days=5` in cache partition |

Downloads are **chunked** (50 tickers) with 1s pause between chunks.

**Also downloaded:** `SPY` (benchmark/regime) and all **sector ETFs** (`ALL_SECTOR_ETFS`) for relative-strength vs sector.

### Fundamentals

**Module:** `src/quant_hub/data/fundamentals/` (via `download_fundamentals()`)

| Field used in scoring | Meaning |
|-----------------------|---------|
| `revenue_yoy` | Blended quarterly revenue YoY (TTM preferred when enough quarters) |
| `eps_combined` | Blended EPS growth metric for scoring tiers |
| `revenue_yoy_status`, `eps_combined_status` | `OK`, `MISSING`, `CAPPED`, `NEGATIVE`, etc. |

Growth values above **300%** are capped (`MAX_REASONABLE_GROWTH = 3.0`) with status `CAPPED` before scoring.

Fundamentals cache TTL: **7 days** (`CACHE_TTL_FUNDAMENTALS_HOURS`).

### Sector mapping

Each eligible ticker gets a **sector ETF** via `resolve_sector_etf(ticker)` for RS vs sector scoring and dashboard display (`sector_etf` field).

---

## 5. Eligibility filters (hard gate)

**Module:** `src/quant_hub/filters/eligibility.py` → `eligibility_detail()`

All checks must pass. First failure stops evaluation (`fail_reason` set).

| # | Rule | Pass condition |
|---|------|----------------|
| 1 | Trading history | ≥ **200** daily bars (`MIN_TRADING_DAYS`) |
| 2 | Minimum price | Close ≥ **$10** (`MIN_PRICE`) |
| 3 | Price stability | Latest close within **3×** of 20-day median close (`PRICE_SPIKE_RATIO`) |
| 4 | Liquidity | 20-day average volume ≥ **750,000** shares (`MIN_AVG_VOLUME`) |
| 5 | Trend alignment | **Price > SMA50 > SMA150 > SMA200** |
| 6 | SMA200 rising | SMA200 today > SMA200 **30 trading days** ago |
| 7 | 52-week low distance | Price ≥ **30%** above 52-week low |
| 8 | 52-week high distance | Price ≤ **25%** below 52-week high |

These filters enforce a **Stage-2-style uptrend** base before breakout scoring runs.

### Fail reason codes

| Code | Dashboard label |
|------|-----------------|
| `insufficient_history` | Fewer than 200 trading days of history |
| `price_below_minimum` | Price below $10 minimum |
| `price_data_anomaly` | Latest price deviates sharply from recent history |
| `low_liquidity` | 20-day average volume below 750,000 shares |
| `trend_misaligned` | Price/MA stack not aligned |
| `sma200_not_rising` | 200-day MA is not rising vs 30 days ago |
| `too_close_to_52w_low` | Price less than 30% above 52-week low |
| `too_far_from_52w_high` | Price more than 25% below 52-week high |
| `no_price_data` | No price data available |

---

## 6. Market regime

**Module:** `src/quant_hub/regime/market.py` — computed from **SPY** daily data.

| Regime | Conditions | Multiplier | Effect on final score |
|--------|------------|------------|------------------------|
| **strong** | SPY > SMA50, SMA50 > SMA200, 63d return > 0 | **1.0** | Full weight |
| **neutral** | Mixed (not strong or weak) | **0.85** | −15% |
| **weak** | SPY < SMA200 **or** >10% below 52w high | **0.6** | −40% |

```text
final_adjusted_score = normalized_score × regime_multiplier
```

Dashboard **Market regime** banner shows: label, SPY price, SMA50/200, 63-day return, distance from 52w high.

A stock can have **normalized ≥ 80** but miss **Tier 1** if `final_adjusted_score < 70` after a weak/neutral regime discount.

---

## 7. Score components (9 factors)

**Max theoretical component sum:** 120 (`RAW_SCORE_MAX`). Some components have lower **achievable** caps in practice (pattern 0–5, resistance 0–5).

Factors run in two passes:

- **Universe pass** — percentile ranks across (or within) the scan universe
- **Ticker pass** — per-stock calculation

### Summary table

| Component | Max pts | Type | What it measures |
|-----------|---------|------|------------------|
| **RS Market** | 20 | Universe percentile | Stock return vs SPY over 63d and 126d |
| **RS Sector** | 15 | Within-sector percentile | Stock return vs sector ETF |
| **Accumulation** | 12 | Universe percentile | Up-day volume ÷ down-day volume (20d) |
| **Relative Volume** | 8 | Ticker | Today / 3-day avg volume vs 20d average |
| **Compression** | 15 | Ticker | Bollinger width squeeze (120d percentile) |
| **Pattern** | 15* | Ticker | 5-point chart base checklist (0–5 pts earned) |
| **Resistance** | 10* | Ticker | Proximity to 50/65-day high (0–5 pts earned) |
| **Revenue** | 15 | Ticker | Revenue YoY growth tiers |
| **EPS** | 15 | Ticker | Combined EPS growth tiers |

\*Factor `max_score` in metadata is 15 / 10; scoring functions cap lower — see below.

---

### RS Market (0–20)

**Ratio:** average of `(stock_return / SPY_return)` over **63** and **126** trading days.

**Score:** percentile rank across **eligible universe** × 20.

- 2+ tickers: full percentile spread  
- 1 ticker: 10 pts (`singleton`)  
- Missing data: 0  

Stored: `scores.rs_market` with raw ratios in `raw.ratio_63d`, `ratio_126d`, `avg_ratio`.

---

### RS Sector (0–15)

**Ratio:** same formula vs mapped **sector ETF**.

**Score:** percentile rank **within each sector ETF group** × 15.

- Group size 1: **7.5** pts neutral (`RS_SECTOR_NEUTRAL`)  
- Missing sector data: 0  

---

### Accumulation (0–12)

**Ratio:** over last **20** days:

```text
accumulation_ratio = sum(volume on up days) / sum(volume on down days)
```

**Score:** universe percentile rank × 12.

Look for ratio **> 1.0** — more volume on up days than down days.

---

### Relative Volume (0–8)

```text
rel_1d = today_volume / avg(prior 20 days)
rel_3d = mean(last 3 days volume) / avg(prior 20 days)
rel_vol = max(rel_1d, rel_3d)
```

| rel_vol | Points |
|---------|--------|
| ≥ 2.0 | 8 |
| ≥ 1.5 | 5 |
| ≥ 1.2 | 3 |
| else | 0 |

---

### Compression (0–15)

**Input:** Bollinger band width `(upper − lower) / mid` over 20 days.

**Logic:** Compare today’s width to the **last 120 days**:

```text
pct_rank = fraction of past 120 widths that are tighter than today
if pct_rank >= 0.5: 0 pts   (not squeezed)
else: 15 × (0.5 − pct_rank) / 0.5
```

Lower percentile = tighter coil = higher score. Tier 1 requires **compression ≥ 8**.

---

### Pattern (0–5 earned, max metadata 15)

**5-point checklist** — +1 pt each:

| Check | Condition |
|-------|-----------|
| Near 52w high | Close ≥ 90% of 52-week high |
| Tight 20d range | (20d high − 20d low) / 20d low ≤ 15% |
| Higher swing lows | Last two swing lows (60d, order=2) rising |
| Short MA stack | SMA10 > SMA20, both rising over 5 bars |
| Holding highs | 20d min close ≥ 88% of 52w high |

---

### Resistance (0–5 earned, max metadata 10)

```text
resistance = max(50-day high, 65-day high)
distance_pct = (resistance − price) / resistance
```

| distance_pct | Points |
|--------------|--------|
| ≤ 3% | 5 |
| ≤ 8% | 3 |
| else | 0 |

Closer to breaking resistance = higher score.

---

### Revenue (0–15)

From `revenue_yoy` (missing → 0):

| YoY growth | Points |
|------------|--------|
| ≥ 40% | 15 |
| ≥ 25% | 12 |
| ≥ 15% | 8 |
| ≥ 5% | 4 |
| negative | 0 (`NEGATIVE`) |
| missing | 0 (`MISSING`) |

Capped growth uses top bucket after cap at 30% for scoring.

---

### EPS (0–15)

From `eps_combined` (missing → 0):

| Combined EPS growth | Points |
|---------------------|--------|
| ≥ 50% | 15 |
| ≥ 30% | 12 |
| ≥ 15% | 8 |
| ≥ 0% | 4 |
| negative | 0 |

Dashboard shows `eps_growth_pct`, `eps_status`, and source details on Ticker Detail.

---

## 8. Aggregate scoring

**Module:** `src/quant_hub/strategies/breakout/aggregate.py`

```text
raw_score          = sum of 9 component scores (+ penalties; breakout has none today)
normalized_score   = (raw_score / RAW_SCORE_MAX) × 100     # RAW_SCORE_MAX = 120
final_adjusted_score = normalized_score × regime_multiplier
```

| Field | Postgres / JSON path | CSV column |
|-------|----------------------|------------|
| Raw | `summary.raw_score` | `raw_score` |
| Normalized | `summary.normalized_score` | `normalized_score` |
| Final | `summary.final_adjusted_score` | `final_adjusted_score` |
| Regime | `summary.regime_multiplier` | `regime_multiplier` |

**Percentile factors** (RS market, RS sector, accumulation) are **relative to the scanned universe** — the same stock can score differently in `sp500` vs `most_actives`.

Component detail for Ticker Detail is built in `src/quant_hub/report/diagnostics.py` → `score_components_detail()` (raw values + plain-English `meaning` per factor).

---

## 9. Tier assignment

**Module:** `src/quant_hub/strategies/breakout/tiers.py`

Only **eligible** tickers are tiered.

### Tier 1 (highest conviction)

**All** must be true:

| Criterion | Threshold |
|-----------|-----------|
| Normalized score | ≥ **80** |
| Final adjusted score | ≥ **70** |
| Compression | ≥ **8** |
| Volume signal | Accumulation ≥ **8** **OR** Relative volume ≥ **5** |

### Tier 2 (watchlist)

- Eligible and **normalized score ≥ 65**
- Does not meet full Tier 1 bar (or would be Tier 1 if all above passed)

### Tier 3

- Eligible but **normalized score < 65**

### Tier explanation

`tier_reason` is human-readable (from `explain_tier()`):

- Tier 1: confirms score, compression, and volume signal  
- Tier 2 with norm ≥ 80: lists which Tier 1 criterion failed (final, compression, volume)  
- Tier 2 otherwise: “Watchlist candidate: normalized score 65–79 range”  
- Tier 3: below watchlist threshold  
- filtered: eligibility fail label  

---

## 10. How to read the dashboard

**Module:** `src/quant_hub/dashboard/viz/pages/breakout.py`

Use **Stock Metrics Cheat Sheet** in the sidebar (`score_guide.py`) for analyst-friendly factor descriptions.

### Tabs

| Tab | Contents |
|-----|----------|
| **Overview** | Takeaway banner, regime panel, tier/exclusion charts, score histogram, heatmap, RS vs compression scatter |
| **Full Universe** | All tickers — sort/filter, component scores, tech vs fund subtotals |
| **Ticker Detail** | Eligibility checks, per-factor scores with raw inputs, fundamentals |
| **Actionable Watchlist** | Tier 1 + Tier 2 only |
| **Compare** | Radar chart for 2–3 tickers |

### Full Universe columns

| Column | Source | How to read |
|--------|--------|-------------|
| **Ticker** | `ticker` | Yahoo Finance link |
| **Tier** | `tier` | Tier 1 / 2 / 3 / filtered |
| **Final** | `summary.final_adjusted_score` | Primary sort — includes regime discount |
| **Norm** | `summary.normalized_score` | Pre-regime 0–100 scale |
| **Raw** | `summary.raw_score` | Sum of components (max ~110 practical) |
| **RS Mkt / RS Sec / …** | `scores.*.score` | Individual component points |
| **Tech / Fund** | sum of technical vs fundamental keys | Quick subtotals |
| **Top signal** | highest components | Short tags for what drove the score |
| **Sector ETF** | `sector_etf` | Benchmark used for RS sector |
| **Filter / reason** | eligibility or `tier_reason` | Why excluded or tier assigned |

### Near-miss panel

**Module:** `ux_helpers.near_miss_dataframe()` — shown when no actionable names or on Actionable tab empty state.

Includes eligible tickers within **~5 points** of thresholds:

| Bucket | Criteria |
|--------|----------|
| Tier 3 near watchlist | Tier 3 and normalized ≥ **60** (65 − 5) |
| Tier 2 almost Tier 1 | Tier 2 and normalized ≥ **80** |
| Final score gap | Tier 2, norm ≥ 65, final between **65–70** (Tier 1 needs final ≥ 70) |

### Reading a Tier 1 example

```text
Tier: Tier 1
Final: 76.5    Norm: 85.0    Regime: neutral (×0.85)
RS Mkt: 16.2   Compression: 12.1   Accumulation: 9.4
tier_reason: Breakout ready: score 85.0 (>=80), adjusted 76.5 (>=70), ...
```

### Reading a filtered example

```text
Tier: filtered
Final: 0
filter_label: Price/MA stack not aligned (price > SMA50 > SMA150 > SMA200)
```

Open **Ticker Detail** → **Eligibility** section for each check’s actual vs threshold.

---

## 11. Storage

### PostgreSQL (system of record)

**Module:** `ScanRepository.upsert_scan()`

| Table | Breakout content |
|-------|------------------|
| **`scan_runs`** | One row per `(scan_date, breakout, universe_id)`; `tier1_count`, `tier2_count`, `tier3_count`, `filtered_count`, `actionable_count`, regime in columns + `metadata` JSON |
| **`ticker_results`** | One row per ticker; full ticker report in **`detail` JSONB** |

Indexed columns: `eligible`, `tier`, `final_score`, `filter_reason`, `sector_etf`.

#### Per-ticker `detail` JSON (representative shape)

```json
{
  "ticker": "XYZ",
  "eligible": true,
  "tier": "Tier 2",
  "tier_reason": "Watchlist candidate: normalized score 72.3 (65-79 range)",
  "sector_etf": "XLK",
  "summary": {
    "raw_score": 86.4,
    "normalized_score": 72.0,
    "regime_multiplier": 0.85,
    "final_adjusted_score": 61.2
  },
  "scores": {
    "rs_market": { "score": 14.2, "max": 20, "raw": { "avg_ratio": 1.15 }, "meaning": "..." },
    "compression": { "score": 11.0, "max": 15, "meaning": "..." }
  },
  "eligibility": {
    "passed": true,
    "fail_reason": null,
    "checks": [ "... 8 eligibility checks ..." ]
  },
  "fundamentals": { "revenue_yoy": 0.22, "eps_combined": 0.31, "..." }
}
```

### File exports

| Output | Path |
|--------|------|
| CSV (full universe) | `data/output/breakout/{universe_id}/scan_results.csv` |
| JSON report | `data/output/breakout/{universe_id}/report.json` |
| Markdown summary | `data/output/breakout/{universe_id}/summary.md` |
| Legacy (sp500) | `data/output/breakout_scan_results.csv`, etc. |

`quant-daily` writes **CSV + JSON + MD** by default.

### Email

**Module:** `notify/email.py` → `send_scan_email()`

- Subject: `Quant Hub YYYY-MM-DD: N Actionable (T1 x, T2 y)`
- Body: regime summary + **Tier 1 & Tier 2** table (final/norm scores, RS, compression, volume)
- Sent even when zero actionable (with “nothing met the bar” note)

---

## 12. Configuration and source code

| Topic | Location |
|-------|----------|
| Eligibility thresholds | `src/quant_hub/config.py`, `filters/eligibility.py` |
| Daily price download + cache | `src/quant_hub/infrastructure/market/yfinance_prices.py` |
| Fundamentals pull + growth math | `src/quant_hub/data/fundamentals/` |
| Factor implementations | `src/quant_hub/factors/` |
| Scoring math | `src/quant_hub/scoring/` |
| Strategy spec + aggregation | `src/quant_hub/strategies/breakout/` |
| Engine orchestration | `src/quant_hub/engine/runner.py` |
| Scan service + CLI | `application/scan_service.py`, `cli/daily.py`, `cli/scan.py` |
| Report JSON for dashboard | `src/quant_hub/report/builder.py`, `report/diagnostics.py` |
| Postgres persistence | `src/quant_hub/infrastructure/postgres/repository.py` |
| Dashboard | `src/quant_hub/dashboard/viz/pages/breakout.py`, `breakout_filters.py`, `score_guide.py` |

### Key constants

| Constant | Value |
|----------|-------|
| `RAW_SCORE_MAX` | 120 |
| `MIN_TRADING_DAYS` | 200 |
| `MIN_PRICE` | $10 |
| `MIN_AVG_VOLUME` | 750,000 |
| `LOOKBACK_DAYS` | 252 |
| `BENCHMARK_TICKER` | SPY |
| Tier 1 normalized / final | ≥ 80 / ≥ 70 |
| Tier 2 normalized | ≥ 65 |
| Tier 1 compression | ≥ 8 |
| Tier 1 volume | accumulation ≥ 8 or rel vol ≥ 5 |

### CLI examples

```bash
quant-daily --universe sp500              # scheduled equivalent + email
quant-daily --universe sp500 --no-email   # no mail
quant-scan --universe sp500 --cache       # manual, JSON report default
quant-scan-all --cache --email            # all universes
```
