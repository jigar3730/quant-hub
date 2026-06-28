# Quant Hub — Administrator Runbook

**Version:** 1.1  
**Audience:** Homelab / platform administrators  
**Install path:** `/opt/stacks/quant-hub`  
**Last updated:** 2026-06-28

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

---

## 1. System overview

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│  quant-hub container (scheduler mode)                   │
│  ├── Streamlit dashboard  :5000 → host :5002            │
│  ├── cron daemon          breakout Mon–Fri 17:17 ET      │
│  │                        swing Fri 18:17 ET             │
│  │                        lynch Sat 09:17 ET              │
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
ls pyproject.toml docker-compose.yml data/universes/sp500.txt
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
docker exec quant-hub quant-scan --universe sp500 --cache
```

Or from host (with venv + DATABASE_URL):

```bash
pip install -e ".[dev,viz]"
quant-scan --universe sp500 --cache
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
docker exec quant-hub quant-daily --universe sp500 --no-cache
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
quant-hub report --universe sp500

# Manual scan with cache
quant-scan --universe sp500 --cache

# Force full price refresh
quant-scan --universe sp500 --cache --force-refresh

# List universes
quant-universe list
quant-universe show sp500 | wc -l   # ticker count

# View logs
tail -f /mnt/fast/quant-data/logs/scan.log
tail -f /mnt/fast/quant-data/logs/cron.log
tail -f /mnt/fast/quant-data/logs/dashboard.log
```

### Docker equivalents

```bash
docker exec quant-hub quant-hub status
docker exec quant-hub quant-scan --universe sp500 --cache
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

Quant Hub ships two active strategies. Both persist to Postgres and can export CSV/JSON; only the commands below send email by default.

| Strategy | CLI | Data | Scoring / output | Email default |
|----------|-----|------|------------------|---------------|
| **Breakout** (daily) | `quant-daily`, `quant-scan`, `quant-scan-all` | ~2y daily OHLCV + fundamentals | Tier 1 / 2 / 3 + filtered; SPY market regime | **ON** for `quant-daily`; **OFF** for `quant-scan` / `quant-scan-all` unless `--email` |
| **Swing** (weekly) | `quant-swing` | 10y weekly OHLCV | `SETUP_LONG` / `SETUP_SHORT` pullbacks | **ON** (use `--no-email` to skip) |
| **Lynch** (fundamental) | `quant-lynch` | Yahoo fundamentals (P/E, PEG, balance sheet) | Fast grower / Stalwart / Asset play categories | **ON** (use `--no-email` to skip) |

**Manual only (no email by default):** ad-hoc `quant-scan` without `--email`.

Configured universes (see `data/universes.json`): `sp500`, `large_cap_growth`, `small_cap_growth`, `mid_cap_growth`, `dividend_growers`, `fintech_growth`, `most_actives`.

### Automated schedule (container cron)

Authoritative file: `docker/crontab`. Reference mirror: `docker/jobs.yaml`.  
Container timezone: `TZ=America/New_York` — cron expressions below are **Eastern Time**.

| Job | Cron | When | Command | Universe | Email |
|-----|------|------|---------|----------|-------|
| **Breakout daily** | `17 17 * * 1-5` | Mon–Fri **5:17 PM ET** | `quant-daily --universe sp500` | `sp500` | Yes (if SMTP set) |
| **Swing weekly** | `17 18 * * 5` | Friday **6:17 PM ET** | `quant-swing --universe sp500` | `sp500` | Yes (if SMTP set) |
| **Lynch weekly** | `17 9 * * 6` | Saturday **9:17 AM ET** | `quant-lynch --universe sp500` | `sp500` | Yes (if SMTP set) |

Crontab entries (stdout/stderr → `/app/logs/cron.log`):

```
17 17 * * 1-5 root . /etc/environment; quant-daily --universe sp500 >> /app/logs/cron.log 2>&1
17 18 * * 5 root . /etc/environment; quant-swing --universe sp500 >> /app/logs/cron.log 2>&1
17 9 * * 6 root . /etc/environment; quant-lynch --universe sp500 >> /app/logs/cron.log 2>&1
```

**Why 5:17 / 6:17 / 9:17?** Breakout and swing run after the US cash close; Lynch runs Saturday morning when fundamentals data is stable and away from weekday price-fetch jobs.

**Not on cron today:** other universes, `quant-scan-all`, or manual-only runs. Add lines to `docker/crontab` if you want them scheduled (stagger by 15–30 minutes).

### What each scheduled job does

#### Breakout — `quant-daily --universe sp500`

1. Resolve `sp500` universe (~193 tickers)
2. Download daily prices (parquet cache ON, 24h TTL) and fundamentals (7-day cache)
3. Compute breakout scores; classify Tier 1 / 2 / 3
4. Derive SPY market regime (label + multiplier)
5. Upsert Postgres `scan_runs` + `ticker_results` for `(today, breakout, sp500)`
6. Write exports: CSV + JSON + MD under `data/output/breakout/sp500/` (plus legacy sp500 copies)
7. Record `job_runs` row (`breakout-sp500-daily`)
8. **Send breakout email** to all `EMAIL_TO` addresses (always sent when SMTP is configured, even if zero actionable tickers)

#### Swing — `quant-swing --universe sp500`

1. Resolve universe tickers
2. Download **weekly** OHLCV (10y history; parquet cache ON by default)
3. For **every ticker:** compute RSI, EMA20/50, ATR, MACD, long/short rule checklists
4. Detect setups when all 5 rules pass on one side (`SETUP_LONG`, `SETUP_SHORT`)
5. Compute **quality score** (partial credit per rule − capped penalties) — see `strategies/swing/scoring.py`
6. Upsert Postgres for `(today, swing, universe)` — full `detail` JSON per ticker
7. Write `setups.csv` under `data/output/swing/{universe}/`
8. Record `job_runs` row (`swing-weekly`)
9. **Send swing email** (always sent when SMTP is configured, even if zero setups)

Rescan all universes after scoring changes:

```bash
bash /opt/stacks/quant-hub/scripts/full-rescan.sh          # breakout + swing + Lynch (truncates DB)
# or swing only:
for u in sp500 large_cap_growth small_cap_growth mid_cap_growth dividend_growers fintech_growth most_actives; do
  docker exec quant-hub quant-swing --universe "$u" --no-email
done
```

Log: `/mnt/fast/quant-data/logs/swing_rescan.log` (if run manually with tee).

#### Lynch — `quant-lynch --universe sp500`

1. Resolve `sp500` universe
2. Fetch Yahoo fundamentals per ticker (P/E, PEG, EPS growth, balance sheet, ownership) — parallel batch
3. Apply anti-filters, base screen, and category classifiers (fast grower / stalwart / asset play)
4. Score each name (Lynch score = % of quantitative checks passed)
5. Upsert Postgres for `(today, lynch, sp500)`
6. Write CSV + JSON + MD under `data/output/lynch/sp500/` (plus legacy `lynch_scan_*` copies)
7. Record `job_runs` row (`lynch-summary-sp500`)
8. **Send Lynch email** — reader-friendly HTML with category summary, top candidates, and qualitative checklist

### Email notifications

Email requires `.env` (or container env): `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO` (comma-separated). Optional: `SMTP_PORT` (587), `EMAIL_FROM`, `SMTP_USE_TLS`.

| Trigger | Subject pattern | Body highlights |
|---------|-----------------|-----------------|
| Breakout (`send_scan_email`) | `Quant Hub YYYY-MM-DD: N Actionable (T1 T1, T2 T2)` | Regime (label, SPY, 63d return); table of **Tier 1 & Tier 2** tickers with norm/final scores, sector ETF, RS, compression, volume; TradingView links |
| Swing (`send_swing_email`) | `Quant Hub Swing YYYY-MM-DD: N setups (L long, S short)` | Weekly data note (10y / 1wk); table of setups with close, EMA20/50, RSI, ATR; TradingView links |
| Lynch (`send_lynch_email`) | `Your Lynch Stock Ideas — Mon DD: N names passed` | Plain-English summary; category count cards; top 20 candidates with company name, Lynch type badges, P/E, PEG, EPS growth, market cap, “why it passed”; qualitative checklist |

Empty results still send mail (“No actionable tickers today” / “No swing setups this week” / Lynch “nothing met the bar”).

**Email defaults by command:**

| Command | Sends email? |
|---------|--------------|
| `quant-daily` | Yes (unless `--no-email`) |
| `quant-swing` | Yes (unless `--no-email`) |
| `quant-lynch` | Yes (unless `--no-email`) |
| `quant-scan` | No |
| `quant-scan-all` | Only with `--email` (one email **per universe** scanned) |

### Manual and batch runs (not scheduled)

```bash
# Single universe breakout — no email unless you add a wrapper or use quant-daily
quant-scan --universe mid_cap_growth --cache

# All universes breakout + email after each (7 emails for 7 universes)
quant-scan-all --cache --email --report both

# Breakout with email for one universe (same as cron job)
quant-daily --universe sp500
quant-daily --universe sp500 --no-email

# Swing for any universe — email ON by default
quant-swing --universe dividend_growers
quant-swing --universe sp500 --no-email

# Lynch fundamental screen — email ON by default
quant-lynch --universe sp500
quant-lynch --universe sp500 --preset fast_grower --no-email

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
   17 17 * * 1-5 root . /etc/environment; quant-daily --universe sp500 >> /app/logs/cron.log 2>&1
   47 17 * * 1-5 root . /etc/environment; quant-daily --universe most_actives >> /app/logs/cron.log 2>&1
   17 18 * * 5 root . /etc/environment; quant-swing --universe sp500 >> /app/logs/cron.log 2>&1
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
  breakout-sp500-daily status=success started=... fetched=193/193
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
WHERE universe_id = 'sp500'
ORDER BY scan_date DESC, scan_time DESC
LIMIT 5;

-- Failed jobs
SELECT * FROM job_runs WHERE status != 'success' ORDER BY started_at DESC LIMIT 10;

-- Ticker count for latest run
SELECT sr.scan_date, COUNT(tr.ticker)
FROM scan_runs sr
JOIN ticker_results tr ON tr.run_id = sr.id
WHERE sr.universe_id = 'sp500'
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
| `UNIVERSE` | No | `sp500` | Override for `entrypoint.sh scan` mode |

### Key paths (inside container)

| Path | Purpose |
|------|---------|
| `/app/data/universes.json` | Universe registry |
| `/app/data/universes/sp500.txt` | Default ticker list |
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

Edit `data/universes/sp500.txt` (or bind-mounted copy), then:

```bash
quant-scan --universe sp500 --cache --force-refresh
```

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
quant-hub report --universe sp500
```

**Fixes:**

```bash
quant-scan --universe sp500 --cache
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
docker exec quant-hub quant-daily --universe sp500 --no-email
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
quant-scan --universe sp500 --cache
```

---

## Quick reference card

```bash
# Health
docker compose ps
quant-hub status

# Manual scan
quant-scan --universe sp500 --cache

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
