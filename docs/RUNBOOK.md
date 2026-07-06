# Quant Hub — Administrator Runbook

**Version:** 1.1  
**Audience:** Homelab / platform administrators  
**Install path:** `/opt/stacks/quant-hub`  
**Last updated:** 2026-06-29

**New operators:** start with [Run Team Quickstart](RUN_TEAM_QUICKSTART.md) — Docker commands, triage, email/schedule/universe recipes.

---

## Table of contents

1. [System overview](#1-system-overview)
2. [Initial deployment](#2-initial-deployment)
3. [Day-to-day operations](#3-day-to-day-operations)
4. [Scans, scheduling, and email](#4-scans-scheduling-and-email)
5. [Monitoring and health checks](#5-monitoring-and-health-checks)
6. [Backup and restore](#6-backup-and-restore)
7. [Configuration reference](#7-configuration-reference)
8. [Common procedures](#8-common-procedures)
9. [Troubleshooting](#9-troubleshooting)
10. [Upgrade and maintenance](#10-upgrade-and-maintenance)
11. [Security notes](#11-security-notes)
12. [Migration from quant-platform](#12-migration-from-quant-platform)
13. [Emergency procedures](#13-emergency-procedures)

**Related:** [Breakout Scanner](BREAKOUT_SCANNER.md) · [Swing Scanner](SWING_SCANNER.md) · [Lynch Scanner](LYNCH_SCANNER.md) · [Data Model / ERD](DATA_MODEL.md) · [Analytics Guide](ANALYTICS_GUIDE.md) · [Junior Dev Database Guide](JUNIOR_DEV_DATABASE_GUIDE.md) · [Architecture Gaps](ARCHITECTURE_GAPS.md) · [Run Team Quickstart](RUN_TEAM_QUICKSTART.md)

---

## 1. System overview

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│  quant-hub container (scheduler mode)                   │
│  ├── Streamlit dashboard  :5000 → host :5002            │
│  ├── cron daemon          daily digest Mon–Fri 17:35 ET     │
│  │                        full coverage Sat 01:00–05:00 ET   │
│  │                        weekly digest Sat 08:00 ET         │
│  └── CLIs: quant-scan, quant-daily, quant-hub, ...      │
└───────────────────────┬─────────────────────────────────┘
                        │ DATABASE_URL
┌───────────────────────▼─────────────────────────────────┐
│  quant-hub-db (Postgres 16)         host :5433           │
│  Tables: scan_runs, ticker_results, job_runs            │
└─────────────────────────────────────────────────────────┘

Persistent volumes (host):
  /mnt/fast/quant-data/postgres   — database files
  /mnt/fast/quant-data/data       — cache, output, universes (bind mount)
  /mnt/fast/quant-data/logs       — scan.log, cron.log, dashboard.log
```

### Services

| Container | Image | Host port | Purpose |
|-----------|-------|-----------|---------|
| `quant-hub-db` | `postgres:16` | 5433 | PostgreSQL |
| `quant-hub` | built from `docker/Dockerfile` | 5002 | App + cron + dashboard |

### Source of truth

**PostgreSQL** holds canonical scan results. CSV/JSON in `data/output/` are exports only.

### Timezone

All containers use `TZ=America/New_York`. Cron runs in Eastern Time.

---

## 2. Initial deployment

### Prerequisites

- Docker and Docker Compose
- `/mnt/fast/quant-data/` writable by Docker
- Python 3.12+ (optional, for host-side CLI without Docker)

### Step 1 — Clone / verify install

```bash
cd /opt/stacks/quant-hub
ls pyproject.toml docker-compose.yml data/universes/sp500_index.txt
```

### Step 2 — Environment file

```bash
cp .env.example .env
```

Edit `.env`:

```bash
POSTGRES_PASSWORD=<strong-password>
DATABASE_URL=postgresql://quant:<strong-password>@postgres:5432/quant_hub
```

For **host-side CLI** (outside Docker), use port 5433:

```bash
export DATABASE_URL=postgresql://quant:<password>@localhost:5433/quant_hub
```

Add to `~/.bashrc` or `/etc/environment` if desired.

### Step 3 — Build and start

```bash
docker compose up -d --build
docker compose ps
```

Expected:

- `quant-hub-db` — **healthy**
- `quant-hub` — **Up**

### Step 4 — Initialize schema

Schema auto-applies on container start via `entrypoint.sh`. Verify manually:

```bash
docker exec quant-hub quant-hub init-db
docker exec quant-hub quant-hub status
```

### Step 5 — First scan

```bash
docker exec quant-hub quant-scan --universe sp500_index --cache
```

Or from host (with venv + DATABASE_URL):

```bash
pip install -e ".[dev,viz]"
quant-scan --universe sp500_index --cache
```

### Step 6 — Verify dashboard

Open `http://<host>:5002`  
Select universe **sp500** and confirm data loads.

### Step 7 — Optional email

Uncomment and set SMTP variables in `.env`, then:

```bash
docker compose up -d --force-recreate quant-hub
```

Test:

```bash
docker exec quant-hub quant-daily --universe sp500_index --no-cache
# Remove --no-cache in production; use for forced test only
```

---

## 3. Day-to-day operations

### Morning checklist (optional)

| Check | Command |
|-------|---------|
| Containers running | `docker compose ps` |
| DB reachable | `quant-hub status` |
| Yesterday's job succeeded | `quant-hub status` → Latest job |
| Cron log clean | `tail -50 /mnt/fast/quant-data/logs/cron.log` |

### Standard operator commands

```bash
# System health
quant-hub status

# Latest scan summary (JSON)
quant-hub report --universe sp500_index

# Manual scan with cache
quant-scan --universe sp500_index --cache

# Force full price refresh
quant-scan --universe sp500_index --cache --force-refresh

# List universes
quant-universe list
quant-universe show sp500 | wc -l   # ticker count
quant-universe refresh sp500_index  # SSGA SPY holdings -> sp500_index.txt (~503 names)

# View logs
tail -f /mnt/fast/quant-data/logs/scan.log
tail -f /mnt/fast/quant-data/logs/cron.log
tail -f /mnt/fast/quant-data/logs/dashboard.log
```

### Docker equivalents

```bash
docker exec quant-hub quant-hub status
docker exec quant-hub quant-scan --universe sp500_index --cache
docker exec -it quant-hub bash
```

### Restart services

```bash
cd /opt/stacks/quant-hub
docker compose restart quant-hub        # app only
docker compose restart postgres         # DB only (brief outage)
docker compose down && docker compose up -d   # full stack
```

---

## 4. Scans, scheduling, and email

### Scan types

Quant Hub ships three active strategies. Both persist to Postgres and can export CSV/JSON; only the commands below send email by default.

| Strategy | CLI | Data | Scoring / output | Email default |
|----------|-----|------|------------------|---------------|
| **Breakout** (daily) | `quant-daily`, `quant-scan`, `quant-scan-all` | ~2y daily OHLCV + fundamentals | Tier 1 / 2 / 3 + filtered; SPY market regime | **ON** for `quant-daily`; **OFF** for `quant-scan` / `quant-scan-all` unless `--email` |
| **Swing** (weekly) | `quant-swing`, `quant-swing-all` | 10y weekly OHLCV | `SETUP_LONG` / `SETUP_SHORT` pullbacks | **ON** (use `--no-email` to skip) |
| **Lynch** (fundamental) | `quant-lynch`, `quant-lynch-all` | Yahoo fundamentals (P/E, PEG, balance sheet) | Fast grower / Stalwart / Asset play categories | **ON** (use `--no-email` to skip) |

**Manual only (no email by default):** ad-hoc `quant-scan` without `--email`.

Configured universes (see `data/universes.json`): `sp500_index`, `sp500_index`, `large_cap_growth`, `small_cap_growth`, `mid_cap_growth`, `dividend_growers`, `fintech_growth`, `most_actives`, `sector_commodity_etfs`.

### Automated schedule (container cron)

Authoritative file: `docker/crontab`. Reference mirror: `docker/jobs.yaml`.  
Container timezone: `TZ=America/New_York` — cron expressions below are **Eastern Time**.

**Email model:** Scans run with `--no-email`. Consolidated digests via `quant-digest` — see [Digest Policy](DIGEST_POLICY.md).

| Job | Cron | When | Command | Email |
|-----|------|------|---------|-------|
| **Breakout daily** | `0 17 * * 1-5` | Mon–Fri **5:00 PM ET** | `quant-daily --universe sp500_index --no-email` | No |
| **Daily digest** | `35 17 * * 1-5` | Mon–Fri **5:35 PM ET** | `quant-digest daily` | **Yes** |
| **ETF breakout** | `30 16 * * 5` | Fri **4:30 PM ET** | `quant-daily --universe sector_commodity_etfs --no-email` | No |
| **ETF swing** | `35 16 * * 5` | Fri **4:35 PM ET** | `quant-swing --universe sector_commodity_etfs --no-email` | No |
| **Swing weekly** | `45 17 * * 5` | Fri **5:45 PM ET** | `quant-swing --universe sp500_index --no-email` | No |
| **SPY holdings refresh** | `30 0 1-7 1,4,7,10 6` | First Sat of quarter **12:30 AM ET** | `quant-universe refresh sp500_index` | No |
| **Breakout full coverage** | `0 1 * * 6` | Sat **1:00 AM ET** | `quant-scan-all --cache --report both` | No |
| **Swing full coverage** | `0 4 * * 6` | Sat **4:00 AM ET** | `quant-swing-all --no-email` | No |
| **Lynch full coverage** | `0 5 * * 6` | Sat **5:00 AM ET** | `quant-lynch-all --no-email` | No |
| **ML labels** | `0 6 * * 6` | Sat **6:00 AM ET** | `quant-ml label --since <90d>` | No |
| **Weekly analytics** | `50 7 * * 6` | Sat **7:50 AM ET** | `quant-analytics weekly` | No |
| **Weekly digest** | `0 8 * * 6` | Sat **8:00 AM ET** | `quant-digest weekly` | **Yes** |
| **Weekly retry** | `0 9 * * 6` | Sat **9:00 AM ET** | `quant-digest weekly` (idempotent) | If needed |

**ML phase note:** When swing ML work is in progress, `docker/crontab` may run only swing sp500 + scoped ML labels. The table above reflects the **full** schedule; see [ML Ops](ML_OPS.md) for the active ML-phase cron.

Crontab entries (stdout/stderr → `/app/logs/cron.log`):

```
0 17 * * 1-5 root . /etc/environment; quant-daily --universe sp500_index --no-email >> /app/logs/cron.log 2>&1
35 17 * * 1-5 root . /etc/environment; quant-digest daily >> /app/logs/cron.log 2>&1
30 16 * * 5 root . /etc/environment; quant-daily --universe sector_commodity_etfs --no-email >> /app/logs/cron.log 2>&1
35 16 * * 5 root . /etc/environment; quant-swing --universe sector_commodity_etfs --no-email >> /app/logs/cron.log 2>&1
45 17 * * 5 root . /etc/environment; quant-swing --universe sp500_index --no-email >> /app/logs/cron.log 2>&1
30 0 1-7 1,4,7,10 6 root . /etc/environment; quant-universe refresh sp500_index >> /app/logs/cron.log 2>&1
0 1 * * 6 root . /etc/environment; quant-scan-all --cache --report both >> /app/logs/cron.log 2>&1
0 4 * * 6 root . /etc/environment; quant-swing-all --no-email >> /app/logs/cron.log 2>&1
0 5 * * 6 root . /etc/environment; quant-lynch-all --no-email >> /app/logs/cron.log 2>&1
0 6 * * 6 root . /etc/environment; quant-ml label --since $(date -d '90 days ago' +\%F) >> /app/logs/cron.log 2>&1
50 7 * * 6 root . /etc/environment; quant-analytics weekly >> /app/logs/cron.log 2>&1
0 8 * * 6 root . /etc/environment; quant-digest weekly >> /app/logs/cron.log 2>&1
0 9 * * 6 root . /etc/environment; quant-digest weekly >> /app/logs/cron.log 2>&1
```

**Why this order?** ETF scans Friday PM; sp500 breakout Mon–Fri 5 PM + daily digest 5:35 PM; Friday sp500 swing feeds weekly digest; Saturday overnight runs full coverage (breakout → swing → Lynch on all universes); quarterly SPY refresh at 12:30 AM before the 1 AM breakout sweep; weekly digest after analytics at 8 AM.

#### Saturday full coverage (all universes)

| Step | Command | Universes |
|------|---------|-----------|
| Breakout | `quant-scan-all --cache --report both` | All 9 in `universes.json` |
| Swing | `quant-swing-all --no-email` | All 9 |
| Lynch | `quant-lynch-all --no-email` | 8 stock universes (`sector_commodity_etfs` skipped via `lynch_enabled: false`) |
| ML labels | `quant-ml label --strategy swing --universe sp500_index --since <90d>` | Forward returns — see [ML Ops](ML_OPS.md) |

Manual equivalent inside the container:

```bash
weekly-full-coverage
# or step-by-step:
quant-scan-all --cache --report both
quant-swing-all --no-email
quant-lynch-all --no-email
```

Digests still highlight **`sp500_index`** only; full coverage populates Postgres and the dashboard for every universe.

### What each scheduled job does

#### Breakout — `quant-daily --universe sp500_index`

1. Resolve `sp500_index` universe (~193 tickers)
2. Download daily prices (parquet cache ON, 24h TTL) and fundamentals (7-day cache)
3. Compute breakout scores; classify Tier 1 / 2 / 3
4. Derive SPY market regime (label + multiplier)
5. Upsert Postgres `scan_runs` + `ticker_results` for `(today, breakout, sp500)`
6. Write exports: CSV + JSON + MD under `data/output/breakout/sp500/` (plus legacy sp500 copies)
7. Record `job_runs` row (`breakout-sp500-index-daily`)
8. **Send breakout email** to all `EMAIL_TO` addresses (always sent when SMTP is configured, even if zero actionable tickers)

**Reference:** [Breakout Scanner — data pipeline](BREAKOUT_SCANNER.md) (eligibility, 9 factors, regime multiplier, tiers, Postgres `detail` JSON, near-miss logic).

#### Swing — `quant-swing --universe sp500_index`

1. Resolve universe tickers
2. Download **weekly** OHLCV (10y history; parquet cache ON by default)
3. For **every ticker:** compute RSI, EMA20/50, ATR, MACD, long/short rule checklists
4. Detect setups when all 5 rules pass on one side (`SETUP_LONG`, `SETUP_SHORT`)
5. Compute **quality score** (partial credit per rule − capped penalties) — see `strategies/swing/scoring.py`
6. Upsert Postgres for `(today, swing, universe)` — full `detail` JSON per ticker
7. Write `setups.csv` under `data/output/swing/{universe}/`
8. Record `job_runs` row (`swing-weekly`)
9. **Send swing email** (always sent when SMTP is configured, even if zero setups)

**Reference:** [Swing Scanner — data pipeline](SWING_SCANNER.md) (setup gate vs quality score, indicator formulas, partial credit, penalties, Postgres `detail` JSON, dashboard columns).

Rescan all universes after scoring changes:

```bash
bash /opt/stacks/quant-hub/scripts/full-rescan.sh          # breakout + swing + Lynch (truncates DB)
# or swing only:
docker exec quant-hub quant-swing-all --no-email
```

Log: `/mnt/fast/quant-data/logs/swing_rescan.log` (if run manually with tee).

#### Lynch — `quant-lynch-all` (Saturday 5:00 AM) + `quant-lynch` (manual)

**Scheduled:** `quant-lynch-all --no-email` runs on all **Lynch-enabled** stock universes (8 today; `sector_commodity_etfs` has `lynch_enabled: false`).

Per universe:

1. Resolve universe tickers
2. Fetch Yahoo fundamentals per ticker (P/E, PEG, EPS growth, balance sheet, ownership) — parallel batch
3. Apply anti-filters, base screen, and category classifiers (fast grower / stalwart / asset play)
4. Score each name (Lynch score = % of quantitative checks passed)
5. Upsert Postgres for `(today, lynch, universe_id)`
6. Write CSV + JSON + MD under `data/output/lynch/{universe_id}/`
7. Record `job_runs` row (`lynch-summary-{preset}-{universe}-batch`)

**Note:** Large universes may hit Yahoo rate limits; some tickers show null Lynch scores. Re-run a single universe manually if needed.

**Reference:** [Lynch Scanner — data pipeline](LYNCH_SCANNER.md) (metrics pull, PEG math, checks, Postgres `detail` JSON, dashboard field mapping).

### Email notifications (consolidated digests)

Email requires `.env`: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO` (comma-separated).

**Scheduled mail:** Only **`quant-digest daily`** (Mon–Fri 5:35 PM) and **`quant-digest weekly`** (Sat 8:00 AM). All cron scans use `--no-email`.

| Digest | Subject pattern | Content |
|--------|-----------------|---------|
| Daily | `Quant Hub Daily YYYY-MM-DD: N conviction, M watchlist` | Regime; Tier 1 table; Tier 2 watchlist (hidden in weak regime); new/dropped; persistent names |
| Weekly | `Quant Hub Weekly YYYY-MM-DD: N triple-alignment names` | Triple alignment; swing A/B highlights; Lynch top; regime recap; ETF tone |

Full rules: [Digest Policy](DIGEST_POLICY.md).

**Manual per-scan email** (optional, not used by cron):

| Command | Sends email? |
|---------|--------------|
| `quant-digest daily` / `weekly` | Yes (unless `--no-email`) |
| `quant-daily` | Yes (unless `--no-email`) |
| `quant-swing` | Yes (unless `--no-email`) |
| `quant-lynch` | Yes (unless `--no-email`) |
| `quant-scan` | No |
| `quant-scan-all` | Only with `--email` (one email **per universe**, 9 today) |
| `quant-swing-all` / `quant-lynch-all` | No (use `--no-email` in cron) |

### Manual and batch runs (not scheduled)

```bash
# Single universe breakout — no email
docker exec quant-hub quant-scan --universe mid_cap_growth --cache

# All universes breakout + email after each (9 emails)
docker exec quant-hub quant-scan-all --cache --email --report both

# Full weekly coverage (breakout + swing + Lynch, no email; ~45–90 min cached)
docker exec quant-hub weekly-full-coverage
# equivalent: docker exec quant-hub bash /app/scripts/weekly-full-coverage.sh

# ML: swing historical backfill + gap report
docker exec quant-hub quant-backfill coverage --universe sp500_index --since 2020-01-01
docker exec quant-hub quant-backfill swing --universe sp500_index --since 2020-01-01

# After DB cleanup — see ML_OPS.md §5 for full ML rebuild (backfill → warm-cache → label)

# Breakout daily workflow for sp500
docker exec quant-hub quant-daily --universe sp500_index --no-email

# Swing / Lynch batch or single universe
docker exec quant-hub quant-swing-all --no-email
docker exec quant-hub quant-lynch-all --no-email
docker exec quant-hub quant-swing --universe dividend_growers --no-email
docker exec quant-hub quant-lynch --universe sp500_index --no-email

# One-shot container entrypoint (no cron)
docker compose run --rm quant-hub scan   # uses UNIVERSE env, default sp500
```

Host-side runs (outside Docker) need `DATABASE_URL=postgresql://quant:<password>@localhost:5433/quant_hub` and the same `.env` SMTP variables.

### Verify cron is running

```bash
docker exec quant-hub ps aux | grep cron
docker exec quant-hub cat /etc/cron.d/quant-hub
tail -50 /mnt/fast/quant-data/logs/cron.log
```

### Add another universe to the schedule

1. Edit `docker/crontab` — **stagger** times to avoid Yahoo rate limits:

   ```
   17 17 * * 1-5 root . /etc/environment; quant-daily --universe sp500_index >> /app/logs/cron.log 2>&1
   47 17 * * 1-5 root . /etc/environment; quant-daily --universe most_actives >> /app/logs/cron.log 2>&1
   17 18 * * 5 root . /etc/environment; quant-swing --universe sp500_index >> /app/logs/cron.log 2>&1
   47 18 * * 5 root . /etc/environment; quant-swing --universe most_actives >> /app/logs/cron.log 2>&1
   ```

2. Mirror changes in `docker/jobs.yaml` for documentation.

3. Rebuild and restart:

   ```bash
   docker compose up -d --build quant-hub
   ```

### Same-day rerun policy

`quant-daily` and `quant-scan` **upsert** on `(scan_date, strategy_id, universe_id)`:

1. Update parent row in `scan_runs`
2. Delete all `ticker_results` for that run
3. Insert fresh ticker rows

Safe to rerun without manual cleanup.

---

## 5. Monitoring and health checks

### CLI status

```bash
quant-hub status
```

Example output:

```
Database: OK
  scan_runs: 3
  ticker_results: 202
  job_runs: 1

Recent scans:
  2026-06-28 sp500 actionable=5 regime=strong

Latest job:
  breakout-sp500-index-daily status=success started=... fetched=193/193
```

### Dashboard System tab

`http://<host>:5002` → **System** tab shows table counts, recent scans, latest job.

### Postgres direct queries

```bash
docker exec -it quant-hub-db psql -U quant -d quant_hub
```

```sql
-- Latest sp500 run
SELECT scan_date, scan_time, actionable_count, tier1_count, tier2_count, regime_label
FROM scan_runs
WHERE universe_id = 'sp500_index'
ORDER BY scan_date DESC, scan_time DESC
LIMIT 5;

-- Failed jobs
SELECT * FROM job_runs WHERE status != 'success' ORDER BY started_at DESC LIMIT 10;

-- Ticker count for latest run
SELECT sr.scan_date, COUNT(tr.ticker)
FROM scan_runs sr
JOIN ticker_results tr ON tr.run_id = sr.id
WHERE sr.universe_id = 'sp500_index'
GROUP BY sr.id, sr.scan_date
ORDER BY sr.scan_date DESC
LIMIT 3;
```

### Log locations

| Log | Path (host) | Contents |
|-----|-------------|----------|
| Scan | `/mnt/fast/quant-data/logs/scan.log` | All breakout runs (`quant-scan`, `quant-daily`, `quant-scan-all`) |
| Swing | `/mnt/fast/quant-data/logs/swing.log` | All `quant-swing` runs |
| Cron | `/mnt/fast/quant-data/logs/cron.log` | Scheduled job stdout/stderr |
| Weekly coverage | `/mnt/fast/quant-data/logs/weekly_coverage.log` | `weekly-full-coverage` script (manual or ad hoc) |
| Dashboard | `/mnt/fast/quant-data/logs/dashboard.log` | Streamlit output |

### What to watch for

| Signal | Healthy | Investigate |
|--------|---------|-------------|
| `Database: OK` | Yes | Connection string, postgres container |
| `job_runs.status` | `success` | `error_message` column, scan.log |
| Cache lines | `Cache hits: N/N` on 2nd run | Missing cache dir permissions |
| `actionable_count` | Stable ± normal variance | Zero for many days, universe file empty |
| Cron log | New entry Mon–Fri ~17:17 ET; Fri ~18:17 ET | Missing entries → cron not running |

---

## 6. Backup and restore

### Postgres (critical)

**Backup:**

```bash
docker exec quant-hub-db pg_dump -U quant quant_hub \
  | gzip > /mnt/fast/quant-data/backups/quant_hub_$(date +%Y%m%d).sql.gz
```

**Restore:**

```bash
gunzip -c /mnt/fast/quant-data/backups/quant_hub_YYYYMMDD.sql.gz \
  | docker exec -i quant-hub-db psql -U quant -d quant_hub
```

Volume path: `/mnt/fast/quant-data/postgres` — include in filesystem backups when DB is stopped or use `pg_dump` for consistency.

### Configuration and universes

Backup these paths:

```
/opt/stacks/quant-hub/.env
/opt/stacks/quant-hub/data/universes.json
/opt/stacks/quant-hub/data/universes/*.txt
```

### Cache (optional)

```
/mnt/fast/quant-data/data/cache/prices/1d/2y/*.parquet
```

Cache is regenerable; backup optional. Deleting cache only increases next scan duration.

### Output exports (optional)

```
/mnt/fast/quant-data/data/output/
```

---

## 7. Configuration reference

### Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | `postgresql://quant:quant@localhost:5432/quant_hub` | Postgres connection |
| `POSTGRES_PASSWORD` | Yes (compose) | `quant` | DB password |
| `TZ` | No | `America/New_York` | Container timezone |
| `SMTP_HOST` | No | — | Email server |
| `SMTP_PORT` | No | `587` | Email port |
| `SMTP_USER` | No | — | SMTP auth user |
| `SMTP_PASSWORD` | No | — | SMTP auth password |
| `EMAIL_FROM` | No | SMTP_USER | From address |
| `EMAIL_TO` | No | — | Comma-separated recipients |
| `SMTP_USE_TLS` | No | `true` | TLS toggle |
| `UNIVERSE` | No | `sp500_index` | Override for `entrypoint.sh scan` mode |

### Key paths (inside container)

| Path | Purpose |
|------|---------|
| `/app/data/universes.json` | Universe registry |
| `/app/data/universes/sp500_index.txt` | Default ticker list |
| `/app/data/cache/prices/1d/2y/` | Per-ticker parquet cache |
| `/app/data/output/` | CSV/JSON/MD exports |
| `/app/logs/` | Application logs |

### Cache behavior

- **Daily (breakout):** TTL 24 hours (file mtime); path `data/cache/prices/1d/2y/`
- **Weekly (swing):** separate parquet cache; enabled by default on `quant-swing` (disable with `--no-cache`)
- **Fundamentals:** 7-day JSON cache at `data/cache/fundamentals/`
- **Chunk size:** 50 tickers per Yahoo batch, 1s pause between chunks
- **Default ON:** `quant-daily`, `quant-swing`
- **Manual breakout:** pass `--cache` on `quant-scan` / `quant-scan-all`

### Database schema

Applied from `src/quant_hub/infrastructure/postgres/schema.sql`:

- `scan_runs` — one row per (scan_date, strategy_id, universe_id)
- `ticker_results` — per-ticker JSONB detail, FK to scan_runs
- `job_runs` — scheduled/manual job audit log

Re-apply safely:

```bash
quant-hub init-db
```

Uses `CREATE TABLE IF NOT EXISTS` — idempotent.

---

## 8. Common procedures

### Full rescan (all strategies × all universes)

**Destructive:** truncates `scan_runs` / `ticker_results` / `job_runs` and clears file exports under `data/output/`.

```bash
bash /opt/stacks/quant-hub/scripts/full-rescan.sh
```

Log: `/mnt/fast/quant-data/logs/full_rescan.log`

### Rebuild dashboard after code changes

```bash
cd /opt/stacks/quant-hub
docker compose build quant-hub
docker compose up -d quant-hub
```

Use `--no-cache` if the container still serves stale Python (Docker layer cache).

### Add a file-based universe

```bash
# 1. Create ticker file
cat > /opt/stacks/quant-hub/data/universes/growth.txt << 'EOF'
NVDA
AMD
AVGO
EOF

# 2. Edit data/universes.json — add:
# "growth": {
#   "name": "Growth Watchlist",
#   "sources": [{"type": "file", "path": "data/universes/growth.txt"}]
# }

# 3. Verify
quant-universe show growth

# 4. First scan
quant-scan --universe growth --cache
```

If using Docker bind mount for `/app/data`, place files under `/mnt/fast/quant-data/data/universes/` instead.

### Update sp500 ticker list

Edit `data/universes/sp500_index.txt` (or bind-mounted copy), then:

```bash
quant-scan --universe sp500_index --cache --force-refresh
```

### Refresh sp500_index from SPY holdings

Full S&P 500 proxy (~503 names) from State Street's daily SPY holdings file:

```bash
quant-universe refresh sp500_index
quant-universe show sp500_index | wc -l
quant-scan --universe sp500_index --cache
```

Cron refreshes automatically on the first Saturday of Jan/Apr/Jul/Oct. Metadata: `data/universes/sp500_index.meta.json`.

### Clear price cache

```bash
rm -rf /mnt/fast/quant-data/data/cache/prices/1d/2y/*.parquet
```

Next scan re-downloads all prices.

### Run tests

```bash
cd /opt/stacks/quant-hub
export DATABASE_URL=postgresql://quant:<password>@localhost:5433/quant_hub
pip install -e ".[dev,viz]"
pytest tests/unit -v
```

### Install CLI on host (without Docker exec)

```bash
cd /opt/stacks/quant-hub
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,viz]"
export DATABASE_URL=postgresql://quant:<password>@localhost:5433/quant_hub
quant-hub status
```

---

## 9. Troubleshooting

### Database: UNREACHABLE

**Symptoms:** `quant-hub status` fails; dashboard shows Postgres error.

**Checks:**

```bash
docker compose ps postgres
docker logs quant-hub-db --tail 50
echo $DATABASE_URL
```

**Fixes:**

- Start postgres: `docker compose up -d postgres`
- Host CLI must use port **5433**, not 5432
- Container CLI must use hostname `postgres`, not `localhost`
- Verify password matches `.env`

---

### Dashboard empty / no scan found

**Checks:**

```bash
quant-hub status
quant-hub report --universe sp500_index
```

**Fixes:**

```bash
quant-scan --universe sp500_index --cache
```

Ensure universe has tickers: `quant-universe show sp500 | wc -l`

---

### Cron did not run

**Checks:**

```bash
docker exec quant-hub ps aux | grep cron
tail -100 /mnt/fast/quant-data/logs/cron.log
docker exec quant-hub quant-hub status
```

**Common causes:**

- `quant-hub` container not running (only postgres up)
- Container started with wrong entrypoint (must default to `scheduler`)
- Clock/timezone — cron uses container local time (ET)

**Fix:**

```bash
docker compose up -d quant-hub
docker exec quant-hub quant-daily --universe sp500_index --no-email
```

---

### Scan slow or Yahoo errors

**Symptoms:** HTTP 404/429 in logs; long runtime.

**Fixes:**

- Use `--cache` (or rely on `quant-daily` default)
- Stagger multiple universe cron jobs
- Retry after delay; avoid parallel scans
- Fundamentals fetch is sequential — expected bottleneck for large universes

---

### job_runs status=failed

**Checks:**

```bash
docker exec quant-hub-db psql -U quant -d quant_hub \
  -c "SELECT job_name, error_message, started_at FROM job_runs ORDER BY started_at DESC LIMIT 3;"
tail -200 /mnt/fast/quant-data/logs/scan.log
```

**Fix:** Address root error (DB down, network, empty universe), then rerun `quant-daily`.

---

### Same-day rerun concerns

No action needed. Upsert is by design. Verify with:

```sql
SELECT scan_date, universe_id, COUNT(*)
FROM scan_runs
GROUP BY scan_date, universe_id, strategy_id
HAVING COUNT(*) > 1;
```

Should return **zero rows**.

---

### Container won't start

```bash
docker compose logs quant-hub --tail 100
docker compose build --no-cache quant-hub
docker compose up -d
```

Missing `.env`: `cp .env.example .env`

---

## 10. Upgrade and maintenance

### Update application code

```bash
cd /opt/stacks/quant-hub
git pull   # if using git
docker compose build quant-hub
docker compose up -d quant-hub
docker exec quant-hub quant-hub init-db   # apply any schema changes
```

### Rotate Postgres password

1. Change password in Postgres
2. Update `.env` `POSTGRES_PASSWORD` and `DATABASE_URL`
3. `docker compose up -d --force-recreate`

### Disk space

Monitor:

```bash
du -sh /mnt/fast/quant-data/postgres
du -sh /mnt/fast/quant-data/data/cache
du -sh /mnt/fast/quant-data/logs
```

Trim old logs:

```bash
truncate -s 0 /mnt/fast/quant-data/logs/cron.log
# or rotate with logrotate
```

### Dependency updates

Rebuild image after `pyproject.toml` changes:

```bash
docker compose build --no-cache quant-hub
```

---

## 11. Security notes

See also **[Architecture Gaps](ARCHITECTURE_GAPS.md)** for the full risk register and remediation phases (C1–C2 cover dashboard and Postgres exposure).

- Change default `POSTGRES_PASSWORD` before production use
- Postgres port 5433 is exposed on host — firewall to trusted networks only
- Dashboard port 5002 has no built-in auth in v1 — place behind reverse proxy with authentication if exposed beyond LAN
- Do not commit `.env` to git
- SMTP credentials live in `.env` only

---

## 12. Migration from quant-platform

Quant Hub runs **in parallel** until validated.

| quant-platform | Quant Hub |
|----------------|-----------|
| Port 5001 | Port 5002 |
| JSON/DuckDB storage | Postgres |
| `quant-scanner` container | `quant-hub` container |

**Cutover checklist:**

- [ ] One week of successful weekday cron in Quant Hub
- [ ] Tier counts roughly match quant-platform for same universe/date
- [ ] Dashboard meets daily workflow needs
- [ ] Email notifications working
- [ ] Backups configured
- [ ] Stop `quant-scanner` and `finance_vibe` containers
- [ ] Keep repos as archive

No automatic historical data migration in v1. Optional one-time JSON import script can be added later.

---

## 13. Emergency procedures

### Stop all scanning

```bash
docker compose stop quant-hub
```

Postgres and historical data remain intact.

### Full stack down

```bash
cd /opt/stacks/quant-hub
docker compose down
```

### Database corrupted / won't start

1. Stop stack: `docker compose down`
2. Restore from latest `pg_dump` backup
3. Or restore `/mnt/fast/quant-data/postgres` volume from snapshot (last resort)
4. `docker compose up -d`
5. `quant-hub init-db && quant-hub status`

### Rebuild from scratch (keep data)

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
quant-hub init-db
```

### Rebuild from scratch (lose scan history)

```bash
docker compose down
sudo rm -rf /mnt/fast/quant-data/postgres/*
docker compose up -d
quant-hub init-db
quant-scan --universe sp500_index --cache
```

---

## Quick reference card

```bash
# Health
docker compose ps
quant-hub status

# Manual scan
quant-scan --universe sp500_index --cache

# Logs
tail -f /mnt/fast/quant-data/logs/cron.log
tail -f /mnt/fast/quant-data/logs/scan.log

# Restart app
docker compose restart quant-hub

# Backup DB
docker exec quant-hub-db pg_dump -U quant quant_hub | gzip > backup.sql.gz
```

---

## Document history

| Date | Change |
|------|--------|
| 2026-06-28 | Initial v1 runbook |
