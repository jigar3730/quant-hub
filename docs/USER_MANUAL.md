# Quant Hub — User Manual

**Version:** 1.1  
**Product:** Quant Hub homelab stock scanner (breakout + swing + Lynch)  
**Audience:** Traders, analysts, and operators who run scans and use the dashboard  
**Last updated:** 2026-06-29 (full universe coverage, batch CLIs, digest schedule)

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
9. [Automated schedule and daily workflow](#9-automated-schedule-and-daily-workflow)
10. [FAQ](#10-faq)

**Deep dive:** [Breakout Scanner](BREAKOUT_SCANNER.md) · [Swing Scanner](SWING_SCANNER.md) · [Lynch Scanner](LYNCH_SCANNER.md) · [Data Model / ERD](DATA_MODEL.md) · [Analytics Guide](ANALYTICS_GUIDE.md) · [Architecture Gaps](ARCHITECTURE_GAPS.md) · [Run Team Quickstart](RUN_TEAM_QUICKSTART.md)

---

## 1. What Quant Hub does

Quant Hub is a **stock scanner** for a homelab environment. It runs two strategies:


| Strategy     | Cadence           | What it finds                                                                          |
| ------------ | ----------------- | -------------------------------------------------------------------------------------- |
| **Breakout** | Daily (weekdays)  | Tier 1 / 2 / 3 names with relative strength, compression, volume, and pattern scores   |
| **Swing**    | Weekly (Friday)   | Long/short pullback setups vs 20-week EMA; **quality score 0–100** ranks setups        |
| **Lynch**    | Weekly (Saturday) | Peter Lynch categories: fast growers, stalwarts, asset plays (P/E, PEG, balance sheet) |


All strategies:

- Load a **named universe** of tickers (e.g. large-cap core list `sp500_index`)
- Download price data from Yahoo Finance (daily for breakout, weekly for swing)
- Store results in **PostgreSQL** (the system of record)
- Display results in a **Streamlit web dashboard** (`quant-view`)
- Can **email** actionable results when SMTP is configured

**v1 scope:** Breakout, swing, and Lynch scanners with Postgres-backed results.

### What you should use it for

- Finding stocks with strong relative strength, compression, volume, and pattern setups
- Reviewing actionable candidates (Tier 1 and Tier 2) after the market close
- Comparing tickers within a universe on a given scan date

### What it is not

- Not a broker or order execution systemasdfsedfas
- Not financial advice
- Not a real-time streaming quote platform (data is daily OHLCV with optional cache)

---

## 2. Getting started

### Access the dashboard

If Quant Hub is running via Docker (recommended):


| Service               | URL                         |
| --------------------- | --------------------------- |
| Dashboard             | `http://<your-server>:5002` |
| Postgres (admin only) | `localhost:5433`            |


The dashboard reads **only from Postgres**. You do not need JSON report files open in the UI.

### First-time check

Ask your administrator to confirm:

1. `docker compose ps` shows `quant-hub` and `quant-hub-db` healthy
2. A scan has been run at least once: `quant-hub status`
3. You can open the dashboard and select universe **sp500_index** with a recent **Scan date**

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


| Control                   | Purpose                                                                                                 |
| ------------------------- | ------------------------------------------------------------------------------------------------------- |
| **Lookup ticker history** | Cross-scan search: when/where a symbol appeared as **actionable** (all strategies, all universes)       |
| **Strategy**              | Breakout (daily), Swing (weekly), or Lynch (fundamental)                                                |
| **Universe**              | Select which ticker list to view (`sp500_index`, `most_actives`, etc.); universes with scans are listed first |
| **Scan date**             | Pick a historical run (up to **500** Fridays — includes ML backfill from ~2020)                         |
| **Filters**               | Strategy-specific (breakout tiers/scores; swing setup type + min RSI; Lynch passed-only)                |
| **Score / rubric guides** | Breakout: stock metrics cheat sheet. Swing: setup quality rubric (partial credit + penalties)           |
| **Search ticker**         | Filter tables by symbol in the current scan                                                             |
| **Ticker Detail picker**  | Open a single-ticker profile; includes **actionable scan history** across all strategies                  |


### Ticker history (accuracy review)

Use **Lookup ticker history** in the sidebar or `quant-hub ticker history SYMBOL` to see every **actionable** appearance:

- Breakout Tier 1/2, Swing setups, Lynch passed, Mean Reversion high conviction
- Lynch rows include point-in-time **institutional %** and analyst count from that scan date
- **Open this scan** jumps to the exact strategy/universe/date snapshot

```bash
quant-hub ticker history NVDA --json
quant-hub ticker show NVDA --strategy lynch --universe sp500_index --date 2024-06-07 --json
```

### Ticker links

All scan tables show a **Ticker** column linking to **Yahoo Finance** quotes (opens in a new tab). Row selection or **Ticker Detail** opens the full scan breakdown (scores, checks, news).

### Breakout tabs


| Tab                      | Description                                                          |
| ------------------------ | -------------------------------------------------------------------- |
| **Overview**             | Today's takeaway, regime, tier charts, near-miss panel, scatter plot |
| **Full Universe**        | Sortable table + side panel preview; top signal tags                 |
| **Ticker Detail**        | Fundamentals, component scores, eligibility, live snapshot           |
| **Actionable Watchlist** | Tier 1 and Tier 2 candidates                                         |
| **Compare**              | Side-by-side radar for 2–3 tickers                                   |
| **System**               | Scan counts and job status (collapsed admin)                         |


Three layers on every breakout result: **eligibility** (hard gate) → **score** (9 factors + regime) → **tier** (Tier 1/2/3). See [Breakout Scanner reference](BREAKOUT_SCANNER.md).

### Swing tabs


| Tab                     | Description                                                                  |
| ----------------------- | ---------------------------------------------------------------------------- |
| **Weekly Setups**       | Confirmed `SETUP_LONG` / `SETUP_SHORT` ranked by **quality score** and grade |
| **Full Universe**       | Every ticker with weekly indicators, rules passed, and score                 |
| **Ticker Detail**       | Setup score breakdown: base components, penalties, rule checklist            |
| **Rejection Breakdown** | Why setups failed (aggregate counts)                                         |


On **Ticker Detail**, see [Swing Scanner reference](SWING_SCANNER.md) for how **Score** (quality) differs from the **setup gate** (all 5 rules must pass).

### Lynch tabs


| Tab               | Description                                                    |
| ----------------- | -------------------------------------------------------------- |
| **Candidates**    | Names that passed the screen (default landing tab)             |
| **Overview**      | Category charts, data-quality panel                            |
| **All Tickers**   | Full universe with Lynch score and data status                 |
| **Ticker Detail** | Plain-English summary, fundamentals table, quantitative checks |


On **Ticker Detail**, three data layers come from the same scan (see [Lynch Scanner reference](LYNCH_SCANNER.md)):

- **Key fundamentals** — curated snapshot with explanations  
- **Quantitative checks** — pass/fail rules and Lynch score inputs  
- **Raw metrics** — full Yahoo-derived field bag (expander)

### Market regime banner

Each scan includes a **market regime** derived from SPY:


| Regime      | Meaning                            | Score effect            |
| ----------- | ---------------------------------- | ----------------------- |
| **strong**  | SPY in uptrend                     | Full weight (×1.0)      |
| **neutral** | Mixed conditions                   | Slight discount (×0.85) |
| **weak**    | Below 200-day MA or far from highs | Larger discount (×0.6)  |


Use regime context when interpreting scores: a Tier 2 in a weak regime may deserve extra caution.

---

## 4. Running scans manually

All scan commands run on the server where Quant Hub is installed (`/opt/stacks/quant-hub`), or inside the container via `docker exec quant-hub …`.

### Scan commands at a glance


| Command                                       | Strategy | Email                  | Typical use                   |
| --------------------------------------------- | -------- | ---------------------- | ----------------------------- |
| `quant-daily --universe sp500_index`                | Breakout | **Yes**                | Same as the weekday cron job  |
| `quant-scan --universe sp500_index --cache`         | Breakout | No                     | Manual scan, no mail          |
| `quant-scan-all --cache --email`              | Breakout | **Yes** (per universe) | Batch all universes           |
| `quant-swing --universe sp500_index`                | Swing    | **Yes**                | Same as the Friday cron job   |
| `quant-swing --universe sp500_index --no-email`     | Swing    | No                     | Manual swing without mail     |
| `quant-swing-all --no-email`                  | Swing    | No                     | All universes (Saturday cron)   |
| `quant-lynch --universe sp500_index --no-email`     | Lynch    | No                     | Single universe               |
| `quant-lynch-all --no-email`                  | Lynch    | No                     | All stock universes (Sat cron)|
| `quant-lynch --preset fast_grower --no-email` | Lynch    | No                     | Narrow preset, no mail        |

On production, prefix with `docker exec quant-hub` (CLI runs inside the container).


### Standard breakout scan (recommended)

```bash
docker exec quant-hub quant-scan --universe sp500_index --cache
```


| Flag               | Meaning                                                                            |
| ------------------ | ---------------------------------------------------------------------------------- |
| `--universe sp500_index` | Use the Large Cap Core list (~193 tickers)                                         |
| `--cache`          | Reuse per-ticker price files cached within 24 hours (faster, fewer Yahoo requests) |
| `--force-refresh`  | Ignore cache and re-download all prices                                            |
| `--dry-run`        | Synthetic data only; no network (for testing)                                      |
| `--report none`    | Skip JSON/MD file export (Postgres still updated unless `--no-persist`)            |
| `--no-persist`     | Skip writing to Postgres (CSV only)                                                |


Scheduled job equivalent: `quant-daily --universe sp500_index` (email on by default). Factor and tier reference: **[BREAKOUT_SCANNER.md](BREAKOUT_SCANNER.md)**.

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

### Swing scan (weekly strategy)

```bash
quant-swing --universe sp500_index
```

Uses 10 years of **weekly** OHLCV. Email is sent by default. Every ticker is persisted with indicators and scoring — not just setups. Results appear under the **Swing** strategy in the dashboard and at `data/output/swing/{universe}/setups.csv`.

```bash
quant-swing --universe dividend_growers --no-email   # skip email
```

#### Swing setup gate vs quality score


| Concept                   | Meaning                                                                                  |
| ------------------------- | ---------------------------------------------------------------------------------------- |
| **Setup gate**            | Hard rule: all 5 long or short checks must pass → `SETUP_LONG` / `SETUP_SHORT`           |
| **Quality score (0–100)** | **Base** partial credit on 5 rules (20 pts each max) **minus penalties** (capped at −25) |
| **Grade**                 | A (85+), B (70+), C (55+), D (<55)                                                       |


A confirmed setup can score below 100 (e.g. 82, grade B) if structure is valid but chase, RSI stretch, or MACD overextension penalties apply. Use the score to **rank** setups and review near-misses in **Full Universe**.

Full reference (indicators, partial-credit tables, dashboard columns): **[SWING_SCANNER.md](SWING_SCANNER.md)**.

Open **Swing setup score rubric** in the sidebar or Weekly Setups tab for the full penalty list.

### Scan all universes (breakout batch)

```bash
quant-scan-all --cache --email --report both
```

Runs breakout on every universe in `data/universes.json` (nine today). With `--email`, you receive **one breakout email per universe** when each finishes.

### Lynch scan (fundamental screen)

```bash
quant-lynch --universe sp500_index
```

Screens for Peter Lynch-style growth-at-a-reasonable-price names. Presets: `summary` (default), `fast_grower`, `stalwart`, `asset_play`, `base`. Email is **on** by default with a reader-friendly summary (category counts, top candidates, qualitative checklist).

Each result includes **plain-English reasoning**: an investor summary paragraph, a fundamentals table explaining what each metric means, and per-check pass/fail sentences (e.g. “PEG 0.8 — meets Lynch hurdle”). Growth for PEG prefers **recent TTM EPS trend** over stale 5-year averages when available.

```bash
quant-lynch --universe sp500_index --preset fast_grower --no-email
```

Results: dashboard **Lynch** strategy, `data/output/lynch/{universe}/`, and legacy `data/output/lynch_scan_report.json` for sp500.

For how PEG, checks, and Postgres storage work, see **[Lynch Scanner — data pipeline](LYNCH_SCANNER.md)**.

### How long does a scan take?


| Scenario                    | Typical duration                 |
| --------------------------- | -------------------------------- |
| Cached sp500_index (~503 tickers) | 1–3 minutes                      |
| Cold cache sp500_index            | 5–15 minutes (Yahoo rate limits) |
| Dry-run                     | Under 10 seconds                 |


Fundamentals are fetched in **parallel batches** (with retries); Yahoo rate limits still dominate runtime on large universes.

### Same-day reruns

Running the scan again on the **same calendar day** for the same universe **replaces** the previous run. You will not get duplicate rows or errors. The latest scores always win.

---

## 5. Understanding scan results

### Tiers


| Tier         | Typical meaning                                                                                                |
| ------------ | -------------------------------------------------------------------------------------------------------------- |
| **Tier 1**   | Highest conviction breakout profile: strong normalized score, compression, and accumulation or relative volume |
| **Tier 2**   | Actionable watchlist: normalized score ≥ 65                                                                    |
| **Tier 3**   | Eligible but lower conviction                                                                                  |
| **filtered** | Failed eligibility (volume, price, data quality, etc.)                                                         |


**Actionable** tickers = Tier 1 + Tier 2.

### Score components

Each eligible ticker is scored on components such as:


| Component           | What it measures                       |
| ------------------- | -------------------------------------- |
| **RS vs Market**    | Relative strength vs SPY               |
| **RS vs Sector**    | Relative strength vs sector ETF        |
| **Accumulation**    | Volume/price accumulation patterns     |
| **Relative Volume** | Today’s volume vs average              |
| **Compression**     | Volatility squeeze / range contraction |
| **Pattern**         | Chart pattern quality                  |
| **Resistance**      | Proximity to breakout levels           |
| **Revenue**         | Revenue growth (fundamentals)          |
| **EPS**             | Earnings growth (fundamentals)         |


Scores are combined into:

- **Raw score** — sum of components  
- **Normalized score** — scaled 0–100  
- **Final adjusted score** — normalized × regime multiplier

Sort and filter primarily on **final adjusted score**.

Full pipeline (eligibility thresholds, factor math, tier rules, dashboard columns): **[BREAKOUT_SCANNER.md](BREAKOUT_SCANNER.md)**.

### Eligibility filters

Tickers marked **filtered** failed checks such as:

- Insufficient trading history  
- Average volume below threshold  
- Price below minimum  
- Missing price data

The **Ticker Detail** tab and **Full Universe** table show the filter reason.

### Swing quality score (weekly strategy)

Fine-grained scoring lives in `setup_detail` on each ticker. **Important:** the **setup gate** (all 5 hard rules pass → `SETUP_LONG` / `SETUP_SHORT`) is separate from the **quality score** (0–100 partial credit minus penalties). A name can score 70+ and still be “No setup” if one rule failed.


| Component       | Max | Notes                                                     |
| --------------- | --- | --------------------------------------------------------- |
| Trend alignment | 20  | EMA20 vs EMA50 spread (partial if flat)                   |
| EMA50 slope     | 20  | Rising/falling vs prior week                              |
| Pullback zone   | 20  | Partial credit by ATR distance from EMA20 band            |
| RSI band        | 20  | Partial credit near band edges                            |
| MACD momentum   | 20  | Two 10-pt sub-parts (week-over-week + overextension trim) |


**Penalties** (examples): chase/extended entry, RSI extreme, MACD overextension, structure break (below EMA50 on longs), wrong-side dominance, weak weekly close.

**Final score** = clamp(base − penalties, 0, 100). Dashboard shows base, each penalty, and per-rule partial credit on **Ticker Detail**.

Full pipeline, indicator formulas, and column-by-column dashboard guide: **[SWING_SCANNER.md](SWING_SCANNER.md)**.

### Lynch fundamentals (weekly strategy)


| Concept         | Meaning                                                             |
| --------------- | ------------------------------------------------------------------- |
| **Lynch score** | % of quantitative checks passed (not a weighted model)              |
| **passed**      | Met preset gate (`summary` = base screen **or** any Lynch category) |
| **categories**  | `fast_grower`, `stalwart`, `asset_play`                             |
| **metrics**     | Raw Yahoo + computed fields (PEG, EPS growth, revenue CV, etc.)     |
| **checks**      | Anti-filters + base/category rules with plain-English explanations  |


Full pipeline: [LYNCH_SCANNER.md](LYNCH_SCANNER.md).

---

## 6. Universes

Universes are defined in `data/universes.json` and backed by files or screeners.

### Built-in universes


| ID                      | Name                     | Source                                                              |
| ----------------------- | ------------------------ | ------------------------------------------------------------------- |
| `sp500_index`           | S&P 500 (SPY holdings)   | SSGA SPY daily holdings file (~503 names; auto-refreshed quarterly) |
| `large_cap_growth`      | Large Cap Growth         | Growth-tilted large-cap watchlist                                   |
| `small_cap_growth`      | Small Cap Growth         | VBK-style holdings                                                  |
| `mid_cap_growth`        | Mid Cap Growth           | Mid cap growth watchlist                                            |
| `dividend_growers`      | Dividend Growers         | Dividend growth proxy                                               |
| `fintech_growth`        | Fintech & Digital Growth | FDIG-style list                                                     |
| `most_actives`          | Most Actives             | Yahoo screener (up to 250 symbols)                                  |
| `sector_commodity_etfs` | Sector & Commodity ETFs  | 11 GICS sector SPDRs + 6 commodity proxies (17 tickers)             |


**Migration note:** The curated `sp500` universe was removed. Historical Postgres rows may still show `universe_id=sp500` for past scan dates; all new scans use `sp500_index` only.


### Refresh a holdings-backed universe

```bash
quant-universe refresh sp500_index          # download SSGA SPY holdings -> sp500_index.txt
quant-universe refresh sp500_index --dry-run
```

Production bind mount: refresh writes to `/mnt/fast/quant-data/data/universes/sp500_index.txt`. Cron refreshes on the **first Saturday of Jan/Apr/Jul/Oct** at **12:30 AM ET** (before the 1 AM breakout sweep).

**`sp500_index`** is the default for weekday scans, digests, and ML jobs.

### Scan all universes (batch)

Run inside the container (`docker exec quant-hub …`) on production:

```bash
quant-scan-all --cache --report both   # breakout, all 9 universes
quant-swing-all --no-email             # swing, all 9 universes
quant-lynch-all --no-email             # Lynch, 8 stock universes (ETFs skipped)
weekly-full-coverage                   # all three in order (~30–90 min cached)
```

| CLI | Universes | Email default |
|-----|-----------|---------------|
| `quant-scan-all` | All 9 | Off (use `--email` for one mail per universe) |
| `quant-swing-all` | All 9 | Off with `--no-email` (cron default) |
| `quant-lynch-all` | 8 stock (`lynch_enabled: false` skips ETFs) | Off with `--no-email` |

Saturday cron runs full coverage automatically (see §9). **`sector_commodity_etfs`** also has dedicated Friday ETF jobs.

### List universes

```bash
quant-universe list
```

### Show tickers in a universe

```bash
quant-universe show sp500_index
```

### Adding a universe (requires admin)

1. Add a ticker file under `data/universes/`
2. Add an entry to `data/universes.json`
3. Run: `quant-scan --universe <new_id> --cache`

No code changes are required for file-based universes.

---

## 7. Exports and reports

Postgres is the **source of truth**. File exports are optional convenience copies.


| Output              | Path                                               | When created                              |
| ------------------- | -------------------------------------------------- | ----------------------------------------- |
| Breakout CSV        | `data/output/breakout/{universe}/scan_results.csv` | Every breakout scan                       |
| Breakout JSON       | `data/output/breakout/{universe}/report.json`      | `quant-daily`, `--report json/both`       |
| Breakout Markdown   | `data/output/breakout/{universe}/summary.md`       | `quant-daily`, `--report md/both`         |
| Swing setups CSV    | `data/output/swing/{universe}/setups.csv`          | Every swing scan                          |
| Lynch CSV / JSON    | `data/output/lynch/{universe}/`                    | Every Lynch scan                          |
| Legacy sp500 copies | `data/output/breakout_scan_`*                      | sp500 breakout only (backward compatible) |


`quant-daily` produces CSV + JSON + MD by default.

### Quick summary from CLI

```bash
quant-hub report --universe sp500_index
```

Prints JSON scan summary from Postgres (tier counts, universe size, etc.).

---

## 8. Email notifications

When SMTP is configured, Quant Hub sends **consolidated digest emails** (see [Digest Policy](DIGEST_POLICY.md)):


| Digest     | When (ET)       | Content                                                                           |
| ---------- | --------------- | --------------------------------------------------------------------------------- |
| **Daily**  | Mon–Fri 5:35 PM | Tier 1 conviction + Tier 2 watchlist; new/dropped; persistent names; regime       |
| **Weekly** | Sat 8:00 AM     | Triple alignment (breakout + swing + Lynch); swing/Lynch highlights; regime recap |


Individual scan emails (`quant-daily`, `quant-swing`, `quant-lynch`) are **off in cron** but available for manual runs.

### SMTP settings (administrator)

- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- `EMAIL_TO` (comma-separated recipients)
- `EMAIL_FROM` (optional)
- `SMTP_USE_TLS` (optional; default `true`)

### Manual email commands


| Command                        | Use                                      |
| ------------------------------ | ---------------------------------------- |
| `quant-digest daily`           | Send today's daily digest                |
| `quant-digest weekly`          | Send weekly digest (after Fri/Sat scans) |
| `quant-daily --universe sp500_index` | Legacy single breakout email             |
| `quant-swing` / `quant-lynch`  | Legacy single-strategy emails            |


Empty-signal days still send a short daily digest when the pipeline ran successfully.

### Legacy per-scan email formats (manual only)

- **Subject:** `Quant Hub YYYY-MM-DD: N Actionable (X T1, Y T2)`
- **Content:** Market regime (label, SPY price, 63-day return); universe stats; HTML table of **Tier 1 and Tier 2** tickers sorted by final score (normalized score, sector ETF, RS, compression, relative volume, tier reason)
- **Links:** Each ticker links to TradingView

### Swing email

- **Subject:** `Quant Hub Swing YYYY-MM-DD: N setups (L long, S short)`
- **Content:** Weekly data context (10y / 1wk); count of long vs short setups; table of `SETUP_LONG` and `SETUP_SHORT` names with close, EMA20/50, RSI, ATR, notes
- **Links:** Each ticker links to TradingView

### Lynch email

- **Subject:** `Your Lynch Stock Ideas — Mon DD: N names passed`
- **Content:** Plain-English intro; colored summary cards (fast growers / stalwarts / asset plays); top candidates with company name, Lynch type badge, score, P/E, PEG, 5Y EPS growth, market cap, and why it passed; “Before you buy” qualitative checklist
- **Links:** Each ticker links to TradingView
- **Empty runs:** Still emailed with guidance to check the dashboard for near-misses

### Skip email for a manual run

```bash
quant-daily --no-email
quant-swing --no-email
quant-lynch --no-email
```

`quant-scan` and `quant-scan-all` (without `--email`) never send mail.

---

## 9. Automated schedule and daily workflow

All scheduled jobs run **inside the `quant-hub` container** in **America/New_York** time. On the host, use `docker exec quant-hub <command>` (the CLI is not on the host PATH unless you install the package locally).

### Production schedule

| Day | Time (ET) | Job | What you receive |
|-----|-----------|-----|------------------|
| Mon–Fri | **5:00 PM** | Breakout (`quant-daily --universe sp500_index --no-email`) | No scan email |
| Mon–Fri | **5:35 PM** | Daily digest (`quant-digest daily`) | **Daily digest email** (sp500 Tier 1/2) |
| Friday | **4:30 PM** | Breakout (`sector_commodity_etfs --no-email`) | Dashboard only |
| Friday | **4:35 PM** | Swing (`sector_commodity_etfs --no-email`) | Dashboard only |
| Friday | **5:45 PM** | Swing (`sp500 --no-email`) | Dashboard only — feeds weekly digest |
| Saturday | **12:30 AM** (quarterly) | `quant-universe refresh sp500_index` | First Sat of Jan/Apr/Jul/Oct |
| Saturday | **1:00 AM** | `quant-scan-all --cache --report both` | Full breakout — all 9 universes → Postgres |
| Saturday | **4:00 AM** | `quant-swing-all --no-email` | Full swing — all 9 universes |
| Saturday | **5:00 AM** | `quant-lynch-all --no-email` | Full Lynch — 8 stock universes |
| Saturday | **7:50 AM** | `quant-analytics weekly` | No email |
| Saturday | **8:00 AM** | `quant-digest weekly` | **Weekly digest email** (sp500 focus) |

### Coverage matrix

| Universe | Breakout | Swing | Lynch |
|----------|----------|-------|-------|
| `sp500_index` | daily + Sat | Fri + Sat | Sat |
| `sp500_index` | Sat | Sat | Sat |
| `large_cap_growth` | Sat | Sat | Sat |
| `small_cap_growth` | Sat | Sat | Sat |
| `mid_cap_growth` | Sat | Sat | Sat |
| `dividend_growers` | Sat | Sat | Sat |
| `fintech_growth` | Sat | Sat | Sat |
| `most_actives` | Sat | Sat | Sat |
| `sector_commodity_etfs` | Fri + Sat | Fri + Sat | — |

Digests highlight **`sp500_index`** only. All universes appear in the dashboard after Saturday overnight runs.

### Typical user routine

**Weekdays (breakout)**

1. After **~5:35 PM ET** — check the **daily digest** email (or open the dashboard)
2. Open `http://<host>:5002`, select **Breakout**, universe **sp500_index**, today’s **Scan date**
3. Review **Actionable Watchlist** (Tier 1 first); use **Ticker Detail** for confirmation

**Fridays (swing + ETFs)**

1. After **~5:45 PM ET** — ETF and sp500 swing scans finish (dashboard only)
2. In the dashboard: **Swing** → **Sector & Commodity ETFs** or **sp500**

**Saturdays (full coverage + weekly digest)**

1. Overnight — all universes scanned (breakout 1 AM, swing 4 AM, Lynch 5 AM ET)
2. After **~8:00 AM ET** — check the **weekly digest** email
3. In the dashboard, pick any **universe** and **strategy**; use the latest **Scan date** for that universe

### Manual full coverage

```bash
docker exec quant-hub weekly-full-coverage
# log: /mnt/fast/quant-data/logs/weekly_coverage.log (or weekly_coverage_manual.log)
```

Expect **~30–90 minutes** cached (longer on cold cache or Lynch rate limits on large universes).

### Manual catch-up (single universe)

If cron failed or you need a refresh:

```bash
docker exec quant-hub quant-daily --universe sp500_index --no-email
docker exec quant-hub quant-swing --universe sp500_index --no-email
docker exec quant-hub quant-lynch --universe sp500_index --no-email
docker exec quant-hub quant-scan --universe large_cap_growth --cache
docker exec quant-hub weekly-full-coverage
```

Same-day reruns replace the previous run for that (date, strategy, universe) — safe to repeat.

---

## 10. FAQ

**Q: The dashboard is empty.**  
A: No scan exists for that universe/date. Run `quant-scan --universe sp500_index --cache` or check `quant-hub status`.

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

**Q: I got an email with no tickers in the table.**  
A: Normal when no names meet Tier 1/2 (breakout) or setup rules (swing). The scan still ran; check the dashboard for filtered names.

**Q: How many emails should I expect on a full batch run?**  
A: `quant-scan-all --email` sends one breakout email per universe (nine today). Batch swing/Lynch use `quant-swing-all` / `quant-lynch-all` (no email in cron). Scheduled mail is only the daily and weekly digests.

**Q: Does the swing job run on weekdays?**  
A: **sp500** and **sector_commodity_etfs** swing run **Friday** (4:35 PM and 5:45 PM ET). All universes get swing on **Saturday 4:00 AM** via `quant-swing-all`.

**Q: Why is Lynch score missing for some tickers?**  
A: Yahoo rate limits on large universes (`sp500_index`, `small_cap_growth`) can leave `lynch_score` null. Re-run `docker exec quant-hub quant-lynch --universe <id> --no-email` for that universe later.

**Q: Where do TradingView links go?**  
A: Email notifications include TradingView chart links for actionable tickers and swing setups.

---

## Glossary


| Term                    | Definition                                                         |
| ----------------------- | ------------------------------------------------------------------ |
| **Universe**            | Named list of tickers to scan                                      |
| **Scan run**            | One complete execution for (date, strategy, universe)              |
| **Regime**              | SPY-based market environment multiplier                            |
| **Actionable**          | Tier 1 or Tier 2 (breakout)                                        |
| **Setup**               | Swing `SETUP_LONG` or `SETUP_SHORT` (all 5 rules pass)             |
| **Swing quality score** | 0–100 setup grade: partial rule credit minus penalties             |
| **Grade**               | A/B/C/D band derived from quality score                            |
| **Near-miss**           | Breakout eligible name close to watchlist threshold (Overview tab) |
| **Cache hit**           | Price loaded from local parquet file (< 24h daily / weekly cache)  |


---

## ML operations

Quant Hub can backfill historical swing scans, compute forward-return labels, and export training Parquet. This is **operator-only** — the dashboard does not run ML jobs.

| Task | Doc |
|------|-----|
| Backfill, label, export, verify | **[ML Ops Guide](ML_OPS.md)** |
| Schema, leakage rules, retention | [ML Foundation](ML_FOUNDATION.md) |

Quick status:

```bash
docker exec quant-hub quant-hub status
docker exec quant-hub quant-ml status
```

---

## Support

For installation, backups, cron failures, and database issues, see **RUNBOOK.md** (administrator guide) or contact your homelab administrator.