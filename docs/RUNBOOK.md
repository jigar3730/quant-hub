# Quant Hub — Administrator Runbook

**Version:** 1.0  
**Audience:** Homelab / platform administrators  
**Install path:** `/opt/stacks/quant-hub`  
**Last updated:** 2026-06-28

---

## Table of contents

1. [System overview](#1-system-overview)
2. [Initial deployment](#2-initial-deployment)
3. [Day-to-day operations](#3-day-to-day-operations)
4. [Scheduled jobs](#4-scheduled-jobs)
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
│  ├── cron daemon          weekday 17:17 ET               │
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

## 4. Scheduled jobs

### Active cron (inside container)

File: `docker/crontab`

```
17 17 * * 1-5 root . /etc/environment; quant-daily --universe sp500 >> /app/logs/cron.log 2>&1
```

| Field | Value |
|-------|-------|
| Schedule | Monday–Friday, 17:17 ET |
| Command | `quant-daily --universe sp500` |
| Cache | **ON** by default |
| Email | **ON** if SMTP configured |
| Job logging | Written to `job_runs` table |

Reference copy: `docker/jobs.yaml` (documentation only; cron reads `crontab`).

### Verify cron is running

```bash
docker exec quant-hub ps aux | grep cron
docker exec quant-hub cat /etc/cron.d/quant-hub
```

### Run daily job manually

```bash
docker exec quant-hub quant-daily --universe sp500
docker exec quant-hub quant-daily --universe sp500 --no-email
```

### Add a second universe on schedule

1. Edit `docker/crontab` — stagger times to avoid Yahoo rate limits:

   ```
   17 17 * * 1-5 root . /etc/environment; quant-daily --universe sp500 >> /app/logs/cron.log 2>&1
   47 17 * * 1-5 root . /etc/environment; quant-daily --universe most_actives >> /app/logs/cron.log 2>&1
   ```

2. Rebuild or copy updated crontab into container and restart:

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
| Scan | `/mnt/fast/quant-data/logs/scan.log` | All `quant-scan` / `quant-daily` runs |
| Cron | `/mnt/fast/quant-data/logs/cron.log` | Scheduled job stdout/stderr |
| Dashboard | `/mnt/fast/quant-data/logs/dashboard.log` | Streamlit output |

### What to watch for

| Signal | Healthy | Investigate |
|--------|---------|-------------|
| `Database: OK` | Yes | Connection string, postgres container |
| `job_runs.status` | `success` | `error_message` column, scan.log |
| Cache lines | `Cache hits: N/N` on 2nd run | Missing cache dir permissions |
| `actionable_count` | Stable ± normal variance | Zero for many days, universe file empty |
| Cron log | New entry weekdays ~17:17 | Missing entries → cron not running |

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

- **TTL:** 24 hours (file mtime)
- **Chunk size:** 50 tickers per Yahoo batch, 1s pause between chunks
- **Default ON:** `quant-daily` only
- **Manual scans:** pass `--cache` explicitly

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
