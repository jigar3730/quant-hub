# Swing Scanner — Data Pipeline Reference

**Version:** 1.0  
**Audience:** Analysts and operators who want to understand how weekly swing data is pulled, calculated, scored, and stored — and how to read the dashboard  
**Last updated:** 2026-06-28

Related docs: [User Manual](USER_MANUAL.md) · [Runbook](RUNBOOK.md) · [Breakout Scanner](BREAKOUT_SCANNER.md) · [Lynch Scanner](LYNCH_SCANNER.md)

---

## Table of contents

1. [Pipeline overview](#1-pipeline-overview)
2. [Two different numbers: setup gate vs quality score](#2-two-different-numbers-setup-gate-vs-quality-score)
3. [Data pull (weekly OHLCV)](#3-data-pull-weekly-ohlcv)
4. [Indicators (calculated fields)](#4-indicators-calculated-fields)
5. [Setup rules (hard gate)](#5-setup-rules-hard-gate)
6. [Quality score (0–100)](#6-quality-score-0100)
7. [How to read the dashboard](#7-how-to-read-the-dashboard)
8. [Storage](#8-storage)
9. [Rejection reasons](#9-rejection-reasons)
10. [Configuration and source code](#10-configuration-and-source-code)

---

## 1. Pipeline overview

```text
Universe tickers
    → download_weekly_prices()          [infrastructure/market/weekly_prices.py]
    → validate_ohlcv()                  [data/quality.py]
    → analyze_swing()                   [strategies/swing/scanner.py]
        → add_indicators()              EMA20, EMA50, RSI, ATR, MACD hist
        → build_long_checks / build_short_checks
        → evaluate_setup()              SETUP_LONG | SETUP_SHORT | none
        → score_swing_quality()         [strategies/swing/scoring.py]
    → analysis_to_report()              Postgres / dashboard JSON
    → Postgres + CSV (setups only) + optional email
```

**Entry point:** `quant-swing` → `SwingScanService.run()` in `src/quant_hub/application/swing_service.py`.

**Cadence:** Weekly bars (`1wk`), **10 years** of history (`10y`). Market regime is fixed to `weekly` (no SPY multiplier like breakout).

Every ticker in the universe is evaluated — not only confirmed setups. Non-setups still get indicators, rule checklists, and a quality score.

---

## 2. Two different numbers: setup gate vs quality score

This is the most important distinction when reading swing results.

| Concept | Field | Meaning |
|---------|-------|---------|
| **Setup gate** | `eligible`, `tier` | **Binary.** All **5 hard rules** on one side must pass → `SETUP_LONG` or `SETUP_SHORT`. Otherwise `tier = filtered`. |
| **Quality score** | `setup_detail.swing_score` | **0–100 continuous.** Partial credit on each rule minus penalties. Computed for **every** ticker with valid weekly data. |
| **Grade** | `setup_detail.quality_label` | Letter band from score: A / B / C / D |
| **Rules passed** | `setup_detail.checks_passed / checks_total` | How many of the **5 scored-side** hard checks passed (e.g. `3/5`) |

### Examples

| Situation | Setup? | Score | How to read it |
|-----------|--------|-------|----------------|
| All 5 long rules pass, clean pullback | `SETUP_LONG` | 92 (A) | Actionable long; high quality |
| All 5 long rules pass, RSI stretched | `SETUP_LONG` | 74 (B) | Actionable long; penalties lowered score |
| 4/5 long rules pass, close near EMA20 | `filtered` | 68 (C) | **Not** a setup — near-miss; score helps rank watchlist |
| Price fetch failed | `filtered` | — | No indicators; see rejection reason |

**Sort confirmed setups by Score (desc).** Use **Full Universe** + score to find near-misses that almost triggered.

---

## 3. Data pull (weekly OHLCV)

**Module:** `src/quant_hub/infrastructure/market/weekly_prices.py`

| Setting | Value | Config constant |
|---------|-------|-----------------|
| History | 10 years | `SWING_PERIOD = "10y"` |
| Bar size | 1 week | `SWING_INTERVAL = "1wk"` |
| Minimum bars | 60 weeks | `SWING_MIN_BARS = 60` |
| Source | Yahoo Finance via `yfinance` | `yf.download(..., auto_adjust=True)` |

### Cache

Weekly OHLCV is cached in **Parquet** under the weekly cache subdirectory (`WEEKLY_CACHE_SUBDIR`). TTL: `CACHE_TTL_WEEKLY_HOURS`. Stale tickers are re-downloaded in chunks of 25 with a 1s pause between chunks.

### Bar hygiene

- Uses **adjusted close** as `Close`.
- **Incomplete current week is dropped** if the last bar’s weekday is not Friday (avoids partial-week signals).
- Required columns after normalize: `Date`, `Open`, `High`, `Low`, `Close`, `Volume`.

### Validation before scoring

**Module:** `src/quant_hub/data/quality.py` → `validate_ohlcv()`

| Check | Swing threshold | Fail reason |
|-------|-----------------|-------------|
| Empty frame | — | `no_price_data` |
| Missing `Date` / `Close` | — | `missing_columns` |
| Row count | ≥ 60 | `insufficient_rows` |
| Latest close NaN | — | `nan_close` |
| Price spike vs 20-bar median | ratio > limit | `price_spike` |
| Last bar age | > 14 days | `stale` |

Failed validation → ticker stored as `filtered` with no indicators.

---

## 4. Indicators (calculated fields)

**Module:** `src/quant_hub/indicators.py` — applied in `add_indicators()` on the weekly OHLCV frame.

All indicators use the **latest completed weekly bar** (`df.iloc[-1]`) unless noted. Rows with NaN indicators are dropped after calculation (`dropna()`), so the scanner needs enough history for warm-up.

| Field | Formula | Parameters | Stored as |
|-------|---------|------------|-----------|
| **EMA20** | Exponential moving average of `Close` | span = 20 weeks | `setup_detail.ema20` |
| **EMA50** | EMA of `Close` | span = 50 weeks | `setup_detail.ema50` |
| **RSI** | Wilder-style RSI on weekly closes | 14 periods | `setup_detail.rsi` |
| **ATR** | Average true range | 14 periods (High/Low/Close) | `setup_detail.atr` |
| **MACD hist** | MACD line − signal line | fast=12, slow=26, signal=9 (weekly bars) | `setup_detail.macd_hist` |
| **MACD hist (prior week)** | Same, previous bar | — | `setup_detail.macd_hist_prev` |
| **Close** | Latest weekly close | — | `setup_detail.close` |
| **bars_evaluated** | Rows after indicator warm-up | — | `setup_detail.bars_evaluated` |

### MACD histogram (detail)

```text
fast_ema  = EMA(Close, 12)
slow_ema  = EMA(Close, 26)
macd_line = fast_ema − slow_ema
signal    = EMA(macd_line, 9)
MACD_Hist = macd_line − signal
```

Momentum rules compare the **last 3 weeks** of histogram values and a **20-week rolling standard deviation** of the histogram (overextension check).

---

## 5. Setup rules (hard gate)

**Module:** `src/quant_hub/strategies/swing/scanner.py`

A setup exists only when **all 5 rules on one side pass** (`evaluate_setup()`). Long is evaluated first; if long fails, short is evaluated.

### Long setup (`SETUP_LONG`)

| # | Rule ID | Label | Pass condition |
|---|---------|-------|----------------|
| 1 | `long_trend` | Uptrend (EMA20 > EMA50) | `EMA20 > EMA50` |
| 2 | `long_ema50_rising` | EMA50 rising | `EMA50 > EMA50_prior_week` |
| 3 | `long_pullback_zone` | Pullback into 20 EMA | `EMA20 ≤ Close ≤ EMA20 × 1.02` |
| 4 | `long_rsi_band` | RSI in long band | `45 ≤ RSI ≤ 60` (default `rsi_min_long=45`) |
| 5 | `long_macd_momentum` | MACD histogram momentum | Rising 2 weeks **and** `MACD_Hist < 2 × std(20w)` |

**MACD long momentum (rule 5):**

- Week-over-week: `hist[-1] > hist[-2]` **and** `hist[-2] > hist[-3]`
- Not overextended: latest histogram < 2 × rolling 20-week std

### Short setup (`SETUP_SHORT`)

| # | Rule ID | Label | Pass condition |
|---|---------|-------|----------------|
| 1 | `short_trend` | Downtrend (EMA20 < EMA50) | `EMA20 < EMA50` |
| 2 | `short_ema50_falling` | EMA50 falling | `EMA50 < EMA50_prior_week` |
| 3 | `short_pullback_zone` | Pullback into 20 EMA | `EMA20 × 0.98 ≤ Close ≤ EMA20` |
| 4 | `short_rsi_band` | RSI in short band | `50 ≤ RSI ≤ 65` |
| 5 | `short_macd_momentum` | MACD histogram momentum | Falling 2 weeks **and** `MACD_Hist > −2 × std(20w)` |

### Scored side (when no setup)

If neither side qualifies, the scanner still picks a **candidate side** for scoring (`scored_side`):

1. Count passes on long vs short (5 rules each).
2. Prefer the side with **more passes**, but the **trend rule** (rule 1) must pass to win that side.
3. Tie-break: long if `long_pass ≥ short_pass`, else short.

Quality score and rule breakdown use this side when there is no confirmed setup.

---

## 6. Quality score (0–100)

**Module:** `src/quant_hub/strategies/swing/scoring.py`

```text
base_score     = sum of 5 rule partial credits (max 100)
penalty_total  = sum of penalties (negative; capped at −25 total)
swing_score    = clamp(base_score + penalty_total, 0, 100)
quality_label  = A / B / C / D from swing_score
```

**Setup gate is separate:** a ticker can score 85 (A) but remain `filtered` if any one hard rule failed.

### Base components (0–20 points each)

#### 1. Trend alignment

Uses EMA spread as % of EMA50: `(EMA20 − EMA50) / EMA50 × 100`.

**Long** (requires EMA20 > EMA50):

| Spread | Points |
|--------|--------|
| ≥ 2.0% | 20 |
| ≥ 1.0% | 16 |
| ≥ 0.3% | 12 |
| > 0 (weak) | 8 |
| EMA20 ≤ EMA50 | 0 |

**Short** (requires EMA20 < EMA50): same tiers on `|spread|`.

#### 2. EMA50 slope

Week-over-week change: `(EMA50 − EMA50_prev) / EMA50_prev × 100`.

**Long:**

| Δ EMA50 | Points | Hard check pass? |
|---------|--------|------------------|
| ≥ +0.2% | 20 | yes |
| ≥ +0.05% | 14 | yes |
| ≥ 0% | 8 | no |
| < 0% | 0 | no |

**Short:** mirror with negative deltas (≤ −0.2% → 20 pts, etc.).

#### 3. Pullback zone

**Long band:** `[EMA20, EMA20 × 1.02]`. **Short band:** `[EMA20 × 0.98, EMA20]`.

| Position | Points (long example) |
|----------|----------------------|
| Inside band | 20 |
| Above band (chasing) | `clamp(20 − 7 × ATR_distance, 0, 18)` |
| Below band | `clamp(16 − 6 × ATR_distance, 0, 16)` |

`ATR_distance` = distance past band edge divided by ATR. Minimum ATR used: `max(ATR, EMA20 × 0.005)`.

#### 4. RSI band

**Long:** target `45–60` (configurable via `rsi_min_long`).

| RSI | Points |
|-----|--------|
| In band | 20 |
| 60–68 (slightly over) | partial down to 6 |
| 39–45 (slightly under) | partial down to 4 |
| > 70 | 0 |
| Else | 4 |

**Short:** target `50–65`; partial credit below 50 or above 65; 0 if RSI < 35.

#### 5. MACD momentum (two 10-point parts)

| Sub-check | Long | Short |
|-----------|------|-------|
| Latest vs prior week | +10 if rising | +10 if falling |
| Prior vs 2 weeks ago | +10 if rising | +10 if falling |
| Overextension trim | −8 if hist ≥ 2× std | −8 if hist ≤ −2× std |

Max 20 points. Hard gate requires full momentum **and** not overextended.

### Penalties (subtracted from base; total capped at −25)

| Code | Label | Long trigger | Short trigger |
|------|-------|--------------|---------------|
| `chase` | Chase / extended | Close > EMA20 × 1.05 (−10) | Close < EMA20 × 0.95 (−10) |
| `extended` | Chase / extended | Above pullback band by > 0.5 ATR (−4 to −8) | (symmetric above band) |
| `rsi_extreme` | RSI extreme | RSI > 72 (−12) or > 68 (−8) | RSI < 32 (−12) or < 38 (−8) |
| `structure_break` | Structure break | Close < EMA50 (−10) | Close > EMA50 (−10) |
| `wrong_side` | Wrong-side dominance | Short rules pass 2+ more than long (−8) | Long rules pass 2+ more than short (−8) |
| `macd_overext` | MACD overextension | Hist ≥ 2× 20w std (−8) | Hist ≤ −2× 20w std (−8) |
| `weak_close` | Weak weekly close | Close in bottom 25% of week range (−5) | Close in top 25% of range (−5) |

If raw penalties exceed 25 points, all penalty amounts are **scaled down** proportionally.

### Quality grades

| Score | Label |
|-------|-------|
| ≥ 85 | **A — High quality** |
| ≥ 70 | **B — Valid setup** |
| ≥ 55 | **C — Near-miss / soft** |
| < 55 | **D — Avoid** |

A confirmed setup can still be grade B or C if penalties apply. A filtered name can be grade C (near-miss) with 4/5 rules passed.

---

## 7. How to read the dashboard

**Module:** `src/quant_hub/dashboard/viz/pages/swing.py`

### Tabs

| Tab | Contents | Sort / filter |
|-----|----------|---------------|
| **Weekly Setups** | Confirmed `SETUP_LONG` / `SETUP_SHORT` only | By **Score** descending |
| **Full Universe** | Every ticker — setups and non-setups | Status, then ticker |
| **Ticker Detail** | Full breakdown for one symbol | Select row or search |
| **Rejection Breakdown** | Counts by fail reason | Aggregate |

Use **Swing Setup Quality Rubric** in the sidebar for the live rubric text (mirrors this doc).

### Table columns

| Column | Source | How to read |
|--------|--------|-------------|
| **Ticker** | `ticker` | Yahoo Finance link |
| **Status** | `tier` | “Long setup” / “Short setup” / “No setup” |
| **Setup** | `tier` | `SETUP_LONG`, `SETUP_SHORT`, or — |
| **Score** | `setup_detail.swing_score` | 0–100 quality (partial credit − penalties) |
| **Grade** | `setup_detail.quality_label` | A / B / C / D band |
| **Close** | `setup_detail.close` | Latest weekly close ($) |
| **RSI** | `setup_detail.rsi` | 14-week RSI |
| **EMA20 / EMA50** | `setup_detail` | Trend levels; compare to Close for pullback |
| **ATR** | `setup_detail.atr` | Weekly volatility; used in pullback partial credit |
| **MACD hist** | `setup_detail.macd_hist` | Latest histogram value |
| **Rules passed** | `checks_passed/checks_total` | Hard checks on scored side (e.g. `5/5`, `3/5`) |
| **Notes / rejection** | `tier_reason` or fail label | Why setup failed or setup note |

### Ticker Detail sections

1. **Metrics row** — Setup score, Close, RSI, EMA20, EMA50, ATR, MACD hist, Rules passed.
2. **Score breakdown** — Base score → each penalty → net penalties → final score.
3. **Rule partial credit** — Each of 5 rules with points earned (0–20), pass/partial/fail badge, threshold text.
4. **Setup rule checklist** — The 5 **hard** pass/fail checks on the primary side (what gates a setup).
5. **Alternate side rules** — Expander with the other side’s 5 checks (for context).

### Reading a long setup example

```text
Status: Long setup          → all 5 long hard checks passed
Score: 78                   → base 86, penalties −8 (e.g. RSI stretch)
Grade: B — Valid setup
Rules passed: 5/5           → hard gate satisfied
Close: $142.50  EMA20: $141.00  → inside [141.00, 143.82] pullback band
RSI: 58                     → inside 45–60 band
```

### Reading a near-miss example

```text
Status: No setup
Score: 64
Grade: C — Near-miss / soft
Rules passed: 4/5           → e.g. MACD momentum failed
Notes: No setup: failed MACD histogram momentum
```

Use **Full Universe**, sort/filter by score, to rank watchlist names that did not quite trigger.

---

## 8. Storage

### PostgreSQL (system of record)

**Module:** `src/quant_hub/infrastructure/postgres/repository.py` → `ScanRepository.upsert_scan()`

| Table | Swing content |
|-------|---------------|
| **`scan_runs`** | One row per `(scan_date, swing, universe_id)`; `tier1_count` = long setups, `tier2_count` = short setups, `filtered_count`, `metadata.setup_long_count`, `setup_short_count`, `filter_breakdown` |
| **`ticker_results`** | **Full universe** — one row per ticker; entire report dict in **`detail` JSONB** |

`final_score` column = `summary.final_adjusted_score` = `swing_score`.

#### Per-ticker `detail` JSON (representative shape)

```json
{
  "ticker": "XYZ",
  "eligible": true,
  "tier": "SETUP_LONG",
  "tier_reason": "Pullback into 20EMA",
  "summary": {
    "swing_score": 78.0,
    "final_adjusted_score": 78.0,
    "rsi": 58.2
  },
  "setup_detail": {
    "close": 142.5,
    "ema20": 141.0,
    "ema50": 135.2,
    "rsi": 58.2,
    "atr": 4.1,
    "macd_hist": 0.0234,
    "macd_hist_prev": 0.0198,
    "bars_evaluated": 480,
    "checks_passed": 5,
    "checks_total": 5,
    "swing_score": 78.0,
    "base_score": 86.0,
    "penalty_total": -8.0,
    "quality_label": "B — Valid setup",
    "scored_side": "long",
    "rule_breakdown": [ "... 5 rows with score/max/threshold ..." ],
    "penalties": [ "... penalty rows with amount/reason ..." ]
  },
  "swing_checks": [ "... all 10 long+short hard checks ..." ],
  "scores": { "... rule scores + indicator levels ..." },
  "eligibility": { "passed": true, "fail_reason": null, "checks": [] }
}
```

### File exports

| Output | Path | Contents |
|--------|------|----------|
| CSV | `data/output/swing/{universe_id}/setups.csv` | **Confirmed setups only** — Symbol, Setup Type, Close, EMA20, EMA50, RSI, ATR, Notes |
| Postgres | — | **Full universe** with scores and checklists |

Email (`send_swing_email`) lists confirmed setups with key indicators; it does not include the full partial-credit breakdown (see dashboard Ticker Detail for that).

### Same-day reruns

Re-running `quant-swing` on the same calendar day for the same universe **replaces** the previous run.

---

## 9. Rejection reasons

**Module:** `SWING_FILTER_LABELS` in `scanner.py`

| Code | Dashboard label | Meaning |
|------|-----------------|---------|
| `no_setup` | No long/short setup matched | Valid data; 1+ hard rules failed on both sides |
| `insufficient_data` | Fewer than 60 weekly bars after indicators | Not enough history after warm-up |
| `no_price_data` | No weekly OHLCV data | Yahoo returned empty |
| `invalid_ohlcv` | OHLCV failed validation | Spike, NaN, etc. |
| `stale_ohlcv` / `stale:*` | Weekly bars are stale | Last bar > 14 days old |
| `missing_columns` | OHLCV missing required columns | Bad download shape |
| `scan_error` | Scanner error during evaluation | Exception during analyze |

**Rejection Breakdown** tab aggregates `filter_breakdown` from `scan_summary`.

---

## 10. Configuration and source code

| Topic | Location |
|-------|----------|
| Weekly period / interval / min bars | `src/quant_hub/config.py` |
| Price download + cache | `src/quant_hub/infrastructure/market/weekly_prices.py` |
| Indicators (EMA, RSI, ATR, MACD) | `src/quant_hub/indicators.py` |
| Setup rules + analysis | `src/quant_hub/strategies/swing/scanner.py` |
| Quality score + penalties | `src/quant_hub/strategies/swing/scoring.py` |
| Scan orchestration | `src/quant_hub/application/swing_service.py` |
| CLI | `src/quant_hub/cli/swing.py` |
| Postgres persistence | `src/quant_hub/infrastructure/postgres/repository.py` |
| Dashboard | `src/quant_hub/dashboard/viz/pages/swing.py`, `swing_filters.py`, `swing_score_guide.py` |
| OHLCV validation | `src/quant_hub/data/quality.py` |

### CLI examples

```bash
quant-swing --universe sp500              # scan + email (default)
quant-swing --universe sp500 --no-email   # scan only
quant-swing-all --no-email                # all universes (Saturday cron)
quant-swing --universe mid_cap_growth --force-refresh  # bypass weekly cache
```

**Scheduled:** Friday **5:45 PM ET** (`sp500` + ETFs at 4:35 PM); **Saturday 4:00 AM ET** full coverage via `quant-swing-all` (see [Runbook](RUNBOOK.md)).
