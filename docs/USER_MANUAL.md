# Quant Hub — User Manual

**Version:** 1.0  
**Product:** Quant Hub homelab breakout scanner  
**Audience:** Traders, analysts, and operators who run scans and use the dashboard  
**Last updated:** 2026-06-28

---

## Table of contents

1. [What Quant Hub does](#1-what-quant-hub-does)
2. [Getting started](#2-getting-started)
3. [The dashboard (`quant-view`)](#3-the-dashboard-quant-view)
4. [Running scans manually](#4-running-scans-manually)
5. [Understanding scan results](#5-understanding-scan-results)
6. [Universes](#6-universes)
7. [Exports and reports](#7-exports-and-reports)
8. [Email notifications](#8-email-notifications)
9. [Daily workflow](#9-daily-workflow)
10. [FAQ](#10-faq)

---

## 1. What Quant Hub does

Quant Hub is a **breakout stock scanner** for a homelab environment. It:

- Loads a **named universe** of tickers (e.g. large-cap core list `sp500`)
- Downloads price and fundamental data from Yahoo Finance
- Scores each ticker on technical and fundamental factors
- Classifies tickers into **Tier 1**, **Tier 2**, **Tier 3**, or **filtered**
- Stores results in **PostgreSQL** (the system of record)
- Displays results in a **Streamlit web dashboard**

**v1 scope:** Breakout strategy only. Lynch, swing, and finance-vibe integrations are planned for future releases.

### What you should use it for

- Finding stocks with strong relative strength, compression, volume, and pattern setups
- Reviewing actionable candidates (Tier 1 and Tier 2) after the market close
- Comparing tickers within a universe on a given scan date

### What it is not

- Not a broker or order execution system
- Not financial advice
- Not a real-time streaming quote platform (data is daily OHLCV with optional cache)

---

## 2. Getting started

### Access the dashboard

If Quant Hub is running via Docker (recommended):

| Service | URL |
|---------|-----|
| Dashboard | `http://<your-server>:5002` |
| Postgres (admin only) | `localhost:5433` |

The dashboard reads **only from Postgres**. You do not need JSON report files open in the UI.

### First-time check

Ask your administrator to confirm:

1. `docker compose ps` shows `quant-hub` and `quant-hub-db` healthy
2. A scan has been run at least once: `quant-hub status`
3. You can open the dashboard and select universe **sp500** with a recent **Scan date**

If the dashboard shows *“No scan found for this universe/date”*, run or wait for a scan (see [Section 4](#4-running-scans-manually)).

---

## 3. The dashboard (`quant-view`)

Launch locally (if not using Docker):

```bash
quant-view
```

Default browser URL when run manually: `http://localhost:8501`  
Docker deployment: `http://<host>:5002`

### Sidebar controls

| Control | Purpose |
|---------|---------|
| **Universe** | Select which ticker list to view (`sp500`, `most_actives`, etc.) |
| **Scan date** | Pick a historical run for that universe (most recent at top) |
| **Tier** | Filter by Tier 1, Tier 2, Tier 3, or filtered |
| **Eligible only** | Hide tickers that failed eligibility filters |
| **Actionable only** | Show Tier 1 + Tier 2 only |
| **Min final score** | Slider to hide low-scoring names |
| **Search ticker** | Jump to a symbol |
| **Score component guide** | Explains RS, compression, volume, etc. |
| **Ticker Detail picker** | Open a single-ticker profile |

### Main tabs

| Tab | Description |
|-----|-------------|
| **Overview** | Summary metrics, regime, tier distribution, heatmaps |
| **Full Universe** | Sortable table of all tickers with scores |
| **Ticker Detail** | Deep dive: fundamentals, technical scores, eligibility |
| **Actionable Watchlist** | Tier 1 and Tier 2 candidates |
| **Compare** | Side-by-side ticker comparison |
| **System** | Scan counts, recent runs, latest scheduled job status |

### Market regime banner

Each scan includes a **market regime** derived from SPY:

| Regime | Meaning | Score effect |
|--------|---------|--------------|
| **strong** | SPY in uptrend | Full weight (×1.0) |
| **neutral** | Mixed conditions | Slight discount (×0.85) |
| **weak** | Below 200-day MA or far from highs | Larger discount (×0.6) |

Use regime context when interpreting scores: a Tier 2 in a weak regime may deserve extra caution.

---

## 4. Running scans manually

All scan commands are run from the server where Quant Hub is installed (`/opt/stacks/quant-hub`).

### Standard scan (recommended)

```bash
quant-scan --universe sp500 --cache
```

| Flag | Meaning |
|------|---------|
| `--universe sp500` | Use the Large Cap Core list (~193 tickers) |
| `--cache` | Reuse per-ticker price files cached within 24 hours (faster, fewer Yahoo requests) |
| `--force-refresh` | Ignore cache and re-download all prices |
| `--dry-run` | Synthetic data only; no network (for testing) |
| `--report none` | Skip JSON/MD file export (Postgres still updated unless `--no-persist`) |
| `--no-persist` | Skip writing to Postgres (CSV only) |

### Scan specific tickers

```bash
quant-scan --tickers NVDA AAPL MSFT --cache
```

### Scan from a custom file

```bash
quant-scan --tickers-file /path/to/my_tickers.txt --cache
```

One ticker per line; `#` starts a comment.

### Resolution priority

When multiple sources are given:

1. `--tickers` (explicit list) — highest priority  
2. `--universe` (named universe from config)  
3. `--tickers-file` (legacy file path)

You must provide at least one of the above.

### How long does a scan take?

| Scenario | Typical duration |
|----------|------------------|
| Cached sp500 (~193 tickers) | 1–3 minutes |
| Cold cache sp500 | 5–15 minutes (Yahoo rate limits) |
| Dry-run | Under 10 seconds |

Fundamentals are fetched **sequentially per ticker** in v1, which dominates runtime on large universes.

### Same-day reruns

Running the scan again on the **same calendar day** for the same universe **replaces** the previous run. You will not get duplicate rows or errors. The latest scores always win.

---

## 5. Understanding scan results

### Tiers

| Tier | Typical meaning |
|------|-----------------|
| **Tier 1** | Highest conviction breakout profile: strong normalized score, compression, and accumulation or relative volume |
| **Tier 2** | Actionable watchlist: normalized score ≥ 65 |
| **Tier 3** | Eligible but lower conviction |
| **filtered** | Failed eligibility (volume, price, data quality, etc.) |

**Actionable** tickers = Tier 1 + Tier 2.

### Score components

Each eligible ticker is scored on components such as:

| Component | What it measures |
|-----------|------------------|
| **RS vs Market** | Relative strength vs SPY |
| **RS vs Sector** | Relative strength vs sector ETF |
| **Accumulation** | Volume/price accumulation patterns |
| **Relative Volume** | Today’s volume vs average |
| **Compression** | Volatility squeeze / range contraction |
| **Pattern** | Chart pattern quality |
| **Resistance** | Proximity to breakout levels |
| **Revenue** | Revenue growth (fundamentals) |
| **EPS** | Earnings growth (fundamentals) |

Scores are combined into:

- **Raw score** — sum of components  
- **Normalized score** — scaled 0–100  
- **Final adjusted score** — normalized × regime multiplier  

Sort and filter primarily on **final adjusted score**.

### Eligibility filters

Tickers marked **filtered** failed checks such as:

- Insufficient trading history  
- Average volume below threshold  
- Price below minimum  
- Missing price data  

The **Ticker Detail** tab and **Full Universe** table show the filter reason.

---

## 6. Universes

Universes are defined in `data/universes.json` and backed by files or screeners.

### Built-in universes (v1)

| ID | Name | Source |
|----|------|--------|
| `sp500` | Large Cap Core | File: `data/universes/sp500.txt` (~193 symbols) |
| `most_actives` | Most Actives | Yahoo screener (up to 250 symbols) |

### List universes

```bash
quant-universe list
```

### Show tickers in a universe

```bash
quant-universe show sp500
```

### Adding a universe (requires admin)

1. Add a ticker file under `data/universes/`  
2. Add an entry to `data/universes.json`  
3. Run: `quant-scan --universe <new_id> --cache`

No code changes are required for file-based universes.

---

## 7. Exports and reports

Postgres is the **source of truth**. File exports are optional convenience copies.

| Output | Path | When created |
|--------|------|--------------|
| CSV results | `data/output/breakout_scan_results.csv` | Every scan |
| JSON report | `data/output/breakout_scan_report.json` | When `--report json` or default |
| Markdown summary | `data/output/breakout_scan_summary.md` | When `--report md` or `both` |

`quant-daily` produces CSV + JSON + MD by default.

### Quick summary from CLI

```bash
quant-hub report --universe sp500
```

Prints JSON scan summary from Postgres (tier counts, universe size, etc.).

---

## 8. Email notifications

When SMTP is configured, `quant-daily` sends an email listing **Tier 1 and Tier 2** tickers after the scan.

Required environment variables (set by administrator in `.env`):

- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- `EMAIL_TO` (comma-separated recipients)
- `EMAIL_FROM` (optional)

Skip email for a manual run:

```bash
quant-daily --no-email
```

---

## 9. Daily workflow

### Automated schedule (production)

On weekdays, the container cron job runs at **5:17 PM Eastern Time**:

```
quant-daily --universe sp500
```

This enables cache, persists to Postgres, writes export files, logs the job, and sends email if configured.

### Typical user routine

1. **After 5:30 PM ET** — open dashboard at `http://<host>:5002`
2. Select **sp500** and today’s **Scan date**
3. Open **Actionable Watchlist** tab
4. Review Tier 1 names first; drill into **Ticker Detail** for confirmation
5. Optionally export CSV from `data/output/` for spreadsheet work

### Manual catch-up

If the cron job failed or you need a refresh:

```bash
quant-scan --universe sp500 --cache
```

Same-day reruns are safe.

---

## 10. FAQ

**Q: The dashboard is empty.**  
A: No scan exists for that universe/date. Run `quant-scan --universe sp500 --cache` or check `quant-hub status`.

**Q: Scores changed after I ran the scan twice today.**  
A: Expected. Same-day reruns replace the canonical run with latest data.

**Q: Why is my ticker “filtered”?**  
A: Open Ticker Detail → Eligibility tab, or check `filter_reason` in the Full Universe table.

**Q: Can I use JSON files instead of Postgres?**  
A: The dashboard does not load JSON in v1. Postgres is required for the UI.

**Q: How fresh is the price data?**  
A: Daily OHLCV; cache TTL is 24 hours per ticker. Use `--force-refresh` for a full re-download.

**Q: Does Quant Hub place trades?**  
A: No. It is research and scanning only.

**Q: Where do TradingView links go?**  
A: Email notifications include TradingView chart links for actionable tickers.

---

## Glossary

| Term | Definition |
|------|------------|
| **Universe** | Named list of tickers to scan |
| **Scan run** | One complete execution for (date, strategy, universe) |
| **Regime** | SPY-based market environment multiplier |
| **Actionable** | Tier 1 or Tier 2 |
| **Cache hit** | Price loaded from local parquet file (< 24h old) |

---

## Support

For installation, backups, cron failures, and database issues, see **RUNBOOK.md** (administrator guide) or contact your homelab administrator.
