# Quant Hub — Analytics Guide

**Version:** 1.0  
**Audience:** Analysts, traders, and operators extracting insights from scan data  
**Last updated:** 2026-06-29

Related: [Data Model / ERD](DATA_MODEL.md) · [User Manual](USER_MANUAL.md) · [Runbook](RUNBOOK.md) · [Breakout](BREAKOUT_SCANNER.md) · [Swing](SWING_SCANNER.md) · [Lynch](LYNCH_SCANNER.md)

---

## Table of contents

1. [What data accumulates](#1-what-data-accumulates)
2. [Where to analyze](#2-where-to-analyze)
3. [Field reference for analysis](#3-field-reference-for-analysis)
4. [Core insight patterns](#4-core-insight-patterns)
5. [SQL cookbook](#5-sql-cookbook)
6. [Python / export analysis](#6-python--export-analysis)
7. [Weekly analyst playbook](#7-weekly-analyst-playbook)
8. [Limitations](#8-limitations)

---

## 1. What data accumulates

### End of day (Mon–Fri, after 5:35 PM ET)

| Asset | Content |
|-------|---------|
| **`scan_runs`** (1 row) | `breakout` + `sp500_index`: tier counts, SPY regime, filter breakdown in `metadata` |
| **`ticker_results`** (~193 rows) | Every sp500 name: `tier`, `final_score`, `sector_etf`, full `detail` JSON (9 factors, eligibility, fundamentals) |
| **Exports** | `data/output/breakout/sp500/scan_results.csv`, `report.json`, `summary.md` |
| **Email** | **Daily digest** (Tier 1 + Tier 2 for sp500 only) |

**One snapshot per calendar day** for `(scan_date, strategy_id, universe_id)`. Rerunning the same day replaces that snapshot (upsert).

### End of week (Friday PM + Saturday overnight)

| When (ET) | Job | Dataset |
|-----------|-----|---------|
| Fri **4:30 PM** | Breakout `sector_commodity_etfs` | ~17 sector/commodity ETFs (breakout scores) |
| Fri **4:35 PM** | Swing `sector_commodity_etfs` | ETF weekly setups + full detail in Postgres |
| Fri **5:45 PM** | Swing `sp500_index` | sp500 swing (feeds weekly digest) |
| Sat **1:00 AM** | Breakout `quant-scan-all` | All 9 universes (~1,950 tickers total) |
| Sat **4:00 AM** | Swing `quant-swing-all` | All 9 universes |
| Sat **5:00 AM** | Lynch `quant-lynch-all` | 8 stock universes (ETFs skipped) |
| Sat **7:50 AM** | `quant-analytics weekly` | Cross-strategy payload for digest |
| Sat **8:00 AM** | Weekly digest email | Triple alignment + highlights (**sp500** focus) |

### Typical week in Postgres

```text
Mon–Fri   5× breakout/sp500 daily runs + 5× daily digest emails
Friday    1× swing/sp500 + 1× breakout/sector_commodity_etfs + 1× swing/sector_commodity_etfs
Saturday  1× breakout (all universes) + 1× swing (all) + 1× Lynch (stock universes)
```

**Richest source:** `ticker_results.detail` (JSONB). CSV exports are flattened subsets. After Saturday runs, every universe has fresh rows for all three strategies (except Lynch on ETFs).

---

## 2. Where to analyze

| Tool | Best for |
|------|----------|
| **Streamlit dashboard** (`http://<host>:5002`) | Same-day exploration, filters, near-miss panel, Lynch score history chart |
| **PostgreSQL** | Time series, cross-strategy joins, aggregates, custom screens |
| **`report.json` exports** | Notebook / pandas without DB |
| **Email** | Daily alerts — not deep analysis |

**Connect to Postgres (host):**

```bash
docker exec -it quant-hub-db psql -U quant -d quant_hub
```

Or: `DATABASE_URL=postgresql://quant:<password>@localhost:5433/quant_hub`

---

## 3. Field reference for analysis

### `scan_runs` — run-level aggregates

| Column | Use in analysis |
|--------|-----------------|
| `scan_date` | Time axis |
| `strategy_id` | `breakout`, `swing`, `lynch` |
| `universe_id` | e.g. `sp500_index`, `sector_commodity_etfs` |
| `tier1_count`, `tier2_count`, `tier3_count`, `filtered_count` | Funnel size |
| `actionable_count` | Breakout T1+T2; swing setups; Lynch passed |
| `regime_label`, `regime_multiplier` | Market context (breakout) |
| `metadata` | JSONB: `market_regime`, `filter_breakdown`, `setup_long_count`, `category_counts`, provenance |

### `ticker_results` — per-symbol rows

| Column | Breakout | Swing | Lynch |
|--------|----------|-------|-------|
| `ticker` | Symbol | Symbol | Symbol |
| `tier` | Tier 1/2/3/filtered | SETUP_LONG / SETUP_SHORT / filtered | fast_grower / stalwart / asset_play / filtered |
| `final_score` | Final adjusted score | Swing quality score | Lynch score |
| `eligible` | Passed eligibility | Has confirmed setup | Passed screen |
| `sector_etf` | RS sector benchmark | — | — |
| `filter_reason` | Fail code | Fail code | Fail code |
| `detail` | 9 factor scores, checks | Rule breakdown, RSI, EMAs | Full metrics, checks |

### Actionable definitions

| Strategy | Treat as actionable |
|----------|---------------------|
| Breakout | `tier IN ('Tier 1', 'Tier 2')` |
| Swing | `tier IN ('SETUP_LONG', 'SETUP_SHORT')` |
| Lynch | `eligible = true` (or `passed` in `detail`) |

### Breakout factor keys (inside `detail.scores`)

`rs_market`, `rs_sector`, `accumulation`, `relative_volume`, `compression`, `pattern`, `resistance`, `revenue`, `eps`

---

## 4. Core insight patterns

### 4.1 Cross-strategy convergence (highest conviction)

**Question:** Which names agree on technical momentum, weekly structure, *and* fundamentals?

**Method:** Join latest Fri breakout T1/T2 + Fri swing setup + Sat Lynch passed on `ticker`.

**Insight:** Short “triple alignment” watchlist — fewer names, higher conviction.

---

### 4.2 Breakout persistence (daily edge)

**Question:** Who stays Tier 1/2 for multiple days vs one-day pops?

**Method:** Count actionable days per ticker over Mon–Fri.

**Insight:** Persistent leaders vs likely fade candidates.

---

### 4.3 New entrants / dropouts (daily diff)

**Question:** Who newly entered or left the actionable list today?

**Method:** Compare today vs yesterday actionable sets (anti-join).

**Insight:** Early momentum shifts before they appear in weekly email habits.

---

### 4.4 Regime-conditioned behavior

**Question:** Should I trust breakout signals more in strong vs weak SPY regimes?

**Method:** Aggregate `actionable_count` and avg `final_score` by `regime_label` from `scan_runs`.

**Insight:** Size conviction or exposure by macro tape (`strong` / `neutral` / `weak`).

---

### 4.5 Factor attribution

**Question:** Is the book driven by relative strength, compression, or volume this week?

**Method:** Average factor scores from `detail.scores` by tier.

**Insight:** What kind of market you’re in (momentum vs coiling vs fundamental-led).

---

### 4.6 Near-miss promotion (breakout)

**Question:** Who is close to actionable but still Tier 3?

**Method:** Tier 3 with high `normalized_score` in `detail.summary` (dashboard near-miss panel uses similar logic).

**Insight:** Early watchlist before promotion to Tier 2.

---

### 4.7 Swing rejection funnel (weekly)

**Question:** More long or short setups? Why are names rejected?

**Method:** `metadata.setup_long_count`, `setup_short_count`, `filter_breakdown` on swing runs.

**Insight:** Market posture (risk-on pullbacks vs defensive shorts).

---

### 4.8 Sector / ETF rotation (Friday)

**Question:** Which sectors show both breakout strength and swing structure?

**Method:** Join `sector_commodity_etfs` breakout + swing on same `scan_date`.

**Insight:** Sector tone for the coming week (XLK, XLE, GLD, etc.).

---

### 4.9 Lynch score drift (weekly)

**Question:** Improving or deteriorating fundamentals?

**Method:** Compare `lynch_score` / `passed` across Saturday runs (dashboard has per-ticker Lynch history chart).

**Insight:** Fundamental momentum independent of price.

---

### 4.10 Data quality monitoring

**Question:** Are Yahoo fetches degrading results?

**Method:** `job_runs`, `metadata.fundamentals_quality`, Lynch `metrics_quality`, spike in `filter_reason = 'no_price_data'`.

**Insight:** Delay decisions or rerun when data quality is poor.

---

## 5. SQL cookbook

Replace dates with your scan dates. Find latest runs:

```sql
SELECT scan_date, strategy_id, universe_id, actionable_count, regime_label
FROM scan_runs
ORDER BY scan_time DESC
LIMIT 15;
```

### 5.1 Today’s actionable breakout names

```sql
SELECT tr.ticker, tr.tier, tr.final_score, tr.sector_etf
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'breakout'
  AND sr.universe_id = 'sp500_index'
  AND sr.scan_date = CURRENT_DATE
  AND tr.tier IN ('Tier 1', 'Tier 2')
ORDER BY tr.final_score DESC;
```

### 5.2 Breakout persistence (last 5 trading days)

```sql
SELECT tr.ticker,
       COUNT(*) AS days_actionable,
       ROUND(AVG(tr.final_score)::numeric, 1) AS avg_score
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'breakout'
  AND sr.universe_id = 'sp500_index'
  AND sr.scan_date >= CURRENT_DATE - INTERVAL '7 days'
  AND tr.tier IN ('Tier 1', 'Tier 2')
GROUP BY tr.ticker
HAVING COUNT(*) >= 3
ORDER BY days_actionable DESC, avg_score DESC;
```

### 5.3 New entrants vs dropouts (day-over-day)

```sql
WITH today AS (
  SELECT tr.ticker
  FROM ticker_results tr
  JOIN scan_runs sr ON sr.id = tr.run_id
  WHERE sr.strategy_id = 'breakout'
    AND sr.universe_id = 'sp500_index'
    AND sr.scan_date = CURRENT_DATE
    AND tr.tier IN ('Tier 1', 'Tier 2')
),
yesterday AS (
  SELECT tr.ticker
  FROM ticker_results tr
  JOIN scan_runs sr ON sr.id = tr.run_id
  WHERE sr.strategy_id = 'breakout'
    AND sr.universe_id = 'sp500_index'
    AND sr.scan_date = CURRENT_DATE - INTERVAL '1 day'
    AND tr.tier IN ('Tier 1', 'Tier 2')
)
SELECT 'new_entrant' AS change_type, ticker FROM today
WHERE ticker NOT IN (SELECT ticker FROM yesterday)
UNION ALL
SELECT 'dropped_out', ticker FROM yesterday
WHERE ticker NOT IN (SELECT ticker FROM today);
```

### 5.4 Cross-strategy convergence (adjust dates to your Fri/Sat runs)

```sql
WITH latest AS (
  SELECT strategy_id,
         MAX(scan_date) AS scan_date
  FROM scan_runs
  WHERE universe_id = 'sp500_index'
    AND strategy_id IN ('breakout', 'swing', 'lynch')
  GROUP BY strategy_id
),
b AS (
  SELECT tr.ticker, tr.tier, tr.final_score
  FROM ticker_results tr
  JOIN scan_runs sr ON sr.id = tr.run_id
  JOIN latest l ON l.strategy_id = 'breakout' AND sr.scan_date = l.scan_date
  WHERE sr.strategy_id = 'breakout' AND sr.universe_id = 'sp500_index'
    AND tr.tier IN ('Tier 1', 'Tier 2')
),
s AS (
  SELECT tr.ticker, tr.tier AS swing_tier, tr.final_score AS swing_score
  FROM ticker_results tr
  JOIN scan_runs sr ON sr.id = tr.run_id
  JOIN latest l ON l.strategy_id = 'swing' AND sr.scan_date = l.scan_date
  WHERE sr.strategy_id = 'swing' AND sr.universe_id = 'sp500_index'
    AND tr.tier IN ('SETUP_LONG', 'SETUP_SHORT')
),
lyn AS (
  SELECT tr.ticker, tr.final_score AS lynch_score
  FROM ticker_results tr
  JOIN scan_runs sr ON sr.id = tr.run_id
  JOIN latest l ON l.strategy_id = 'lynch' AND sr.scan_date = l.scan_date
  WHERE sr.strategy_id = 'lynch' AND sr.universe_id = 'sp500_index'
    AND tr.eligible = true
)
SELECT b.ticker,
       b.tier AS breakout_tier,
       b.final_score AS breakout_score,
       s.swing_tier,
       s.swing_score,
       lyn.lynch_score,
       CASE
         WHEN s.ticker IS NOT NULL AND lyn.ticker IS NOT NULL THEN 'triple'
         WHEN s.ticker IS NOT NULL THEN 'breakout+swing'
         WHEN lyn.ticker IS NOT NULL THEN 'breakout+lynch'
         ELSE 'breakout_only'
       END AS alignment
FROM b
LEFT JOIN s USING (ticker)
LEFT JOIN lyn USING (ticker)
WHERE s.ticker IS NOT NULL OR lyn.ticker IS NOT NULL
ORDER BY alignment, b.final_score DESC;
```

### 5.5 Regime summary (breakout runs)

```sql
SELECT sr.scan_date,
       sr.regime_label,
       sr.regime_multiplier,
       sr.actionable_count,
       sr.tier1_count,
       sr.tier2_count
FROM scan_runs sr
WHERE sr.strategy_id = 'breakout'
  AND sr.universe_id = 'sp500_index'
  AND sr.scan_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY sr.scan_date DESC;
```

### 5.6 Average breakout factor scores by tier (JSONB)

```sql
SELECT tr.tier,
       COUNT(*) AS n,
       ROUND(AVG((tr.detail->'scores'->'rs_market'->>'score')::float)::numeric, 1) AS avg_rs_market,
       ROUND(AVG((tr.detail->'scores'->'compression'->>'score')::float)::numeric, 1) AS avg_compression,
       ROUND(AVG((tr.detail->'scores'->'relative_volume'->>'score')::float)::numeric, 1) AS avg_rel_vol
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'breakout'
  AND sr.universe_id = 'sp500_index'
  AND sr.scan_date = (
    SELECT MAX(scan_date) FROM scan_runs
    WHERE strategy_id = 'breakout' AND universe_id = 'sp500_index'
  )
  AND tr.tier IN ('Tier 1', 'Tier 2', 'Tier 3')
GROUP BY tr.tier
ORDER BY tr.tier;
```

### 5.7 Swing quality leaders (full universe in Postgres)

```sql
SELECT tr.ticker,
       tr.tier,
       tr.final_score AS swing_score,
       tr.detail->'setup_detail'->>'quality_label' AS grade,
       (tr.detail->'setup_detail'->>'rsi')::float AS rsi
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'swing'
  AND sr.universe_id = 'sp500_index'
  AND sr.scan_date = (
    SELECT MAX(scan_date) FROM scan_runs
    WHERE strategy_id = 'swing' AND universe_id = 'sp500_index'
  )
  AND tr.tier IN ('SETUP_LONG', 'SETUP_SHORT')
ORDER BY tr.final_score DESC
LIMIT 25;
```

### 5.8 Lynch pass list with categories

```sql
SELECT tr.ticker,
       tr.final_score AS lynch_score,
       tr.detail->'categories' AS categories,
       (tr.detail->>'pe_ratio')::float AS pe,
       (tr.detail->>'peg_ratio')::float AS peg
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'lynch'
  AND sr.universe_id = 'sp500_index'
  AND sr.scan_date = (
    SELECT MAX(scan_date) FROM scan_runs
    WHERE strategy_id = 'lynch' AND universe_id = 'sp500_index'
  )
  AND tr.eligible = true
ORDER BY tr.final_score DESC NULLS LAST;
```

### 5.9 Lynch score history for one ticker

```sql
SELECT sr.scan_date,
       tr.final_score AS lynch_score,
       tr.eligible AS passed,
       tr.detail->'categories' AS categories
FROM ticker_results tr
JOIN scan_runs sr ON sr.id = tr.run_id
WHERE sr.strategy_id = 'lynch'
  AND tr.ticker = 'AAPL'
ORDER BY sr.scan_date DESC
LIMIT 12;
```

### 5.10 ETF sector rotation (Friday)

```sql
SELECT b.ticker,
       b.tier AS breakout_tier,
       b.final_score AS breakout_score,
       s.tier AS swing_tier,
       s.final_score AS swing_score
FROM ticker_results b
JOIN scan_runs sr_b ON sr_b.id = b.run_id
JOIN ticker_results s ON s.ticker = b.ticker
JOIN scan_runs sr_s ON sr_s.id = s.run_id
WHERE sr_b.strategy_id = 'breakout'
  AND sr_b.universe_id = 'sector_commodity_etfs'
  AND sr_s.strategy_id = 'swing'
  AND sr_s.universe_id = 'sector_commodity_etfs'
  AND sr_b.scan_date = sr_s.scan_date
  AND sr_b.scan_date = (
    SELECT MAX(scan_date) FROM scan_runs
    WHERE strategy_id = 'breakout' AND universe_id = 'sector_commodity_etfs'
  )
  AND (b.tier IN ('Tier 1', 'Tier 2') OR s.tier IN ('SETUP_LONG', 'SETUP_SHORT'))
ORDER BY b.final_score DESC NULLS LAST;
```

### 5.11 Filter breakdown (why names excluded)

```sql
SELECT sr.scan_date,
       sr.metadata->'filter_breakdown' AS filter_breakdown,
       sr.metadata->'eligible_count' AS eligible,
       sr.metadata->'excluded_count' AS excluded
FROM scan_runs sr
WHERE sr.strategy_id = 'breakout'
  AND sr.universe_id = 'sp500_index'
ORDER BY sr.scan_date DESC
LIMIT 10;
```

---

## 6. Python / export analysis

### Load latest JSON report (no DB)

```python
import json
from pathlib import Path

path = Path("/mnt/fast/quant-data/data/output/breakout/sp500/report.json")
report = json.loads(path.read_text())
tickers = report["tickers"]
actionable = [t for t in tickers if t.get("tier") in ("Tier 1", "Tier 2")]
df = __import__("pandas").DataFrame([
    {
        "ticker": t["ticker"],
        "tier": t["tier"],
        "final_score": t["summary"]["final_adjusted_score"],
        "sector_etf": t.get("sector_etf"),
    }
    for t in actionable
])
print(df.sort_values("final_score", ascending=False).head(20))
```

### Pandas via Postgres

```python
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine("postgresql://quant:<password>@localhost:5433/quant_hub")
df = pd.read_sql("""
    SELECT sr.scan_date, tr.ticker, tr.tier, tr.final_score
    FROM ticker_results tr
    JOIN scan_runs sr ON sr.id = tr.run_id
    WHERE sr.strategy_id = 'breakout' AND sr.universe_id = 'sp500_index'
      AND tr.tier IN ('Tier 1', 'Tier 2')
    ORDER BY sr.scan_date, tr.final_score DESC
""", engine)
# Pivot: tickers × dates
pivot = df.pivot_table(index="ticker", columns="scan_date", values="final_score", aggfunc="first")
```

**Note:** Forward-return backtesting is **not built in**. To validate signals, join `scan_date` + `ticker` to future price data externally.

---

## 7. Weekly analyst playbook

| When | Action | Output |
|------|--------|--------|
| **Mon–Fri PM** | Review breakout email; note persistent T1/T2 names | Daily watchlist |
| **Mon–Fri** | Optional: SQL 5.2 persistence + 5.3 new/drop | Momentum leaders |
| **Friday PM** | Swing setups + quality grades (dashboard or SQL 5.7) | Weekly technical setups |
| **Friday PM** | ETF breakout + swing (SQL 5.10) | Sector tone |
| **Saturday AM** | Weekly digest email; dashboard for any universe/strategy (Sat overnight full coverage) | Cross-universe insight |
| **Saturday AM** | Lynch data for all stock universes in dashboard (SQL 5.8 per universe) | Fundamental candidates |
| **Weekend** | Cross-strategy convergence (SQL 5.4) | **Primary insight list** |
| **Weekend** | Regime summary (SQL 5.5) + factor attribution (5.6) | Context for sizing |

### Recommended “solid insight” workflow

1. Run **cross-strategy convergence** (§5.4) — start with `alignment = 'triple'`.
2. Filter triple names to **breakout Tier 1 only** and **swing quality A/B** (`detail.setup_detail.quality_label`).
3. Check **regime** — prefer full size when `regime_label = 'strong'`.
4. Review **persistence** — names actionable 3+ days this week rank higher.
5. Export final list to CSV from dashboard or SQL for the trading week.

---

## 8. Limitations

| Limitation | Impact |
|------------|--------|
| One snapshot per day per strategy/universe | No intraday analysis |
| Same-day rerun overwrites | No multiple runs per day preserved |
| Swing CSV = setups only | Use Postgres for full swing universe analytics |
| Breakout score history | Stored in Postgres; dashboard shows latest run only (Lynch history chart exists) |
| No forward P&amp;L | You must join signals to future prices for backtests |
| Yahoo data quality | Scores can be stale or null on fetch failures — check `job_runs` and filter breakdown; Lynch batch runs may rate-limit on large universes |
| Retention | History grows until manual prune — see [Architecture Gaps](ARCHITECTURE_GAPS.md) |

---

## Related files

| Topic | Path |
|-------|------|
| Schema | `src/quant_hub/infrastructure/postgres/schema.sql` |
| Repository queries | `src/quant_hub/infrastructure/postgres/repository.py` |
| Lynch history API | `repository.lynch_ticker_history()` |
| Breakout exports | `data/output/breakout/{universe_id}/report.json` |
| Swing setups CSV | `data/output/swing/{universe_id}/setups.csv` |
