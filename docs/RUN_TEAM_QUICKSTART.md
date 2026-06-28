# Quant Hub — Run Team Quickstart

**Version:** 1.0  
**Audience:** Day-to-day operators (run team)  
**Install path:** `/opt/stacks/quant-hub`  
**Last updated:** 2026-06-28

**Start here.** Full detail: [Runbook](RUNBOOK.md) · Analyst guide: [User Manual](USER_MANUAL.md)

---

## 1. What you are running

| Component | Container | Host access | Purpose |
|-----------|-----------|-------------|---------|
| **App** | `quant-hub` | Dashboard `http://<host>:5002` | Streamlit UI + cron + scan CLIs |
| **Database** | `quant-hub-db` | Postgres `localhost:5433` | Canonical scan results |

**Three strategies:** Breakout (daily), Swing (weekly), Lynch (fundamental).  
**Timezone:** All cron jobs run in **America/New_York (ET)**.

---

## 2. Critical paths (read this first)

There are **two locations** for data. Editing the wrong one is the #1 ops mistake.

| What | Repo path (git) | **Live path (Docker uses this)** |
|------|-----------------|----------------------------------|
| Universe registry | `/opt/stacks/quant-hub/data/universes.json` | `/mnt/fast/quant-data/data/universes.json` |
| Ticker lists | `/opt/stacks/quant-hub/data/universes/*.txt` | `/mnt/fast/quant-data/data/universes/*.txt` |
| Scan exports | — | `/mnt/fast/quant-data/data/output/` |
| Price cache | — | `/mnt/fast/quant-data/data/cache/` |
| Logs | — | `/mnt/fast/quant-data/logs/` |
| Postgres data | — | `/mnt/fast/quant-data/postgres/` |
| Secrets / SMTP | `/opt/stacks/quant-hub/.env` | Loaded at container start (not bind-mounted) |

**Rule:** For universe or ticker changes in production, edit files under **`/mnt/fast/quant-data/data/`** (or copy from repo after editing, then verify).

**Config / code / cron changes** live in the repo: `/opt/stacks/quant-hub/` → rebuild container when needed.

---

## 3. Docker — standard commands

All commands assume:

```bash
cd /opt/stacks/quant-hub
```

### 3.1 Stack lifecycle

| Task | Command |
|------|---------|
| Start stack | `docker compose up -d` |
| Start + rebuild image | `docker compose up -d --build` |
| Stop stack | `docker compose down` |
| Restart app only | `docker compose restart quant-hub` |
| Restart DB only | `docker compose restart postgres` |
| View running services | `docker compose ps` |
| View resource usage | `docker stats quant-hub quant-hub-db` |

### 3.2 Logs

| Task | Command |
|------|---------|
| App container logs | `docker compose logs quant-hub --tail 100` |
| Follow app logs | `docker compose logs -f quant-hub` |
| Postgres logs | `docker compose logs quant-hub-db --tail 50` |
| Cron log (host) | `tail -100 /mnt/fast/quant-data/logs/cron.log` |
| Scan log (host) | `tail -100 /mnt/fast/quant-data/logs/scan.log` |
| Dashboard log (host) | `tail -50 /mnt/fast/quant-data/logs/dashboard.log` |
| Follow cron log | `tail -f /mnt/fast/quant-data/logs/cron.log` |

### 3.3 Shell and exec

| Task | Command |
|------|---------|
| Shell inside app | `docker exec -it quant-hub bash` |
| Shell inside DB | `docker exec -it quant-hub-db psql -U quant -d quant_hub` |
| Run CLI in container | `docker exec quant-hub quant-hub status` |
| One-off scan (no cron) | `docker compose run --rm quant-hub scan` |

### 3.4 Build and deploy code changes

When Python code, `docker/crontab`, or `Dockerfile` changes:

```bash
cd /opt/stacks/quant-hub
git pull                    # if using git deploy
docker compose build quant-hub
docker compose up -d quant-hub
docker exec quant-hub quant-hub status
```

Force clean rebuild if the container serves stale code:

```bash
docker compose build --no-cache quant-hub
docker compose up -d quant-hub
```

### 3.5 Environment / secrets reload

`.env` is read when the container is **created**, not on simple restart.

| Task | Command |
|------|---------|
| Apply `.env` changes (email, passwords) | `docker compose up -d --force-recreate quant-hub` |
| Verify env inside container | `docker exec quant-hub printenv \| grep -E '^(SMTP_|EMAIL_|DATABASE_)'` |

**Do not commit `.env` to git.**

### 3.6 Database backup (manual)

```bash
mkdir -p /mnt/fast/quant-data/backups
docker exec quant-hub-db pg_dump -U quant quant_hub \
  | gzip > /mnt/fast/quant-data/backups/quant_hub_$(date +%Y%m%d).sql.gz
```

Restore: see [Runbook §6](RUNBOOK.md#6-backup-and-restore).

### 3.7 Health check at a glance

```bash
docker compose ps                          # quant-hub-db should be "healthy"
docker exec quant-hub quant-hub status     # Database: OK + recent scans
docker exec quant-hub ps aux | grep cron   # cron daemon running
curl -s -o /dev/null -w "%{http_code}" http://localhost:5002   # expect 200
```

---

## 4. Top 10 daily commands

```bash
cd /opt/stacks/quant-hub

# 1. Are containers up?
docker compose ps

# 2. Is the database OK? Any recent scans?
docker exec quant-hub quant-hub status

# 3. Did cron run cleanly?
tail -50 /mnt/fast/quant-data/logs/cron.log

# 4. Manual breakout scan (same as weekday job, no email)
docker exec quant-hub quant-daily --universe sp500 --no-email

# 5. Manual swing scan
docker exec quant-hub quant-swing --universe sp500 --no-email

# 6. Manual Lynch scan
docker exec quant-hub quant-lynch --universe sp500 --no-email

# 7. List configured universes
docker exec quant-hub quant-universe list

# 8. Show tickers in a universe
docker exec quant-hub quant-universe show sp500 | wc -l

# 9. Restart app after issues
docker compose restart quant-hub

# 10. Open dashboard
# http://<host>:5002  →  select Strategy, Universe, Scan date
```

**Host-side CLI** (optional, outside Docker): install with `pip install -e ".[dev,viz]"` and set  
`DATABASE_URL=postgresql://quant:<password>@localhost:5433/quant_hub`.

---

## 5. Scheduled jobs (ET)

Authoritative file: `docker/crontab`. After edits → `docker compose up -d --build quant-hub`.

| Job | When | Command | Email |
|-----|------|---------|-------|
| Breakout daily | Mon–Fri **5:17 PM** | `quant-daily --universe sp500` | Yes |
| ETF breakout | Fri **4:30 PM** | `quant-daily --universe sector_commodity_etfs --no-email` | No |
| ETF swing | Fri **4:35 PM** | `quant-swing --universe sector_commodity_etfs --no-email` | No |
| Swing weekly | Fri **6:17 PM** | `quant-swing --universe sp500` | Yes |
| Lynch weekly | Sat **9:17 AM** | `quant-lynch --universe sp500` | Yes |

Verify cron:

```bash
docker exec quant-hub cat /etc/cron.d/quant-hub
docker exec quant-hub ps aux | grep cron
tail -50 /mnt/fast/quant-data/logs/cron.log
```

---

## 6. Common change recipes

### 6.1 Add or remove email recipients

1. Edit `/opt/stacks/quant-hub/.env`:

   ```bash
   EMAIL_TO=person1@example.com,person2@example.com
   ```

   Also ensure `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` are set.

2. Recreate the app container (required for cron to pick up new env):

   ```bash
   cd /opt/stacks/quant-hub
   docker compose up -d --force-recreate quant-hub
   ```

3. Test (optional — sends real email):

   ```bash
   docker exec quant-hub quant-daily --universe sp500
   ```

4. Confirm in logs: `grep -i email /mnt/fast/quant-data/logs/scan.log | tail -5`

**Per-job email control:** cron lines use `--no-email` to skip mail (see ETF jobs above). Manual runs: add `--no-email` to any CLI.

---

### 6.2 Change scan schedule or add a universe to cron

1. Edit **`/opt/stacks/quant-hub/docker/crontab`** — **stagger times** to avoid Yahoo rate limits (e.g. `:17`, `:47`).

   Example — add daily breakout for `most_actives` at 5:47 PM ET Mon–Fri:

   ```
   47 17 * * 1-5 root . /etc/environment; quant-daily --universe most_actives >> /app/logs/cron.log 2>&1
   ```

2. Mirror the job in **`docker/jobs.yaml`** (documentation only).

3. Rebuild and restart:

   ```bash
   cd /opt/stacks/quant-hub
   docker compose up -d --build quant-hub
   ```

4. Verify:

   ```bash
   docker exec quant-hub cat /etc/cron.d/quant-hub
   ```

**Cron syntax reminder:** `minute hour day month weekday` — container timezone is ET.

---

### 6.3 Add a new universe (ticker list)

1. Create ticker file on the **live data mount**:

   ```bash
   cat > /mnt/fast/quant-data/data/universes/my_watchlist.txt << 'EOF'
   AAPL
   MSFT
   NVDA
   EOF
   ```

2. Add entry to **`/mnt/fast/quant-data/data/universes.json`**:

   ```json
   "my_watchlist": {
     "name": "My Watchlist",
     "description": "Custom operator list",
     "sources": [{"type": "file", "path": "data/universes/my_watchlist.txt"}]
   }
   ```

3. Verify and run first scan:

   ```bash
   docker exec quant-hub quant-universe show my_watchlist
   docker exec quant-hub quant-scan --universe my_watchlist --cache
   ```

4. Optional: commit repo copies under `/opt/stacks/quant-hub/data/` for git backup.

---

### 6.4 Update tickers in an existing universe (e.g. sp500)

1. Edit **`/mnt/fast/quant-data/data/universes/sp500.txt`** (one symbol per line).

2. Rescan:

   ```bash
   docker exec quant-hub quant-scan --universe sp500 --cache --force-refresh
   ```

Same-day reruns **upsert** — safe to run again without DB cleanup.

---

### 6.5 Apply code / config update from git

```bash
cd /opt/stacks/quant-hub
git pull
docker compose build quant-hub
docker compose up -d quant-hub
docker exec quant-hub quant-hub status
pytest tests/unit -q    # optional, from host with DATABASE_URL set
```

---

## 7. Triage guide

| Symptom | First checks | Likely fix |
|---------|--------------|------------|
| **Dashboard shows DB error** | `docker compose ps`; `docker exec quant-hub quant-hub status` | `docker compose up -d postgres`; verify `.env` password |
| **Dashboard: "No scan found"** | `quant-hub status`; pick correct universe/date in sidebar | `docker exec quant-hub quant-daily --universe sp500 --cache` |
| **Cron didn't run** | `docker compose ps`; `tail -100 .../cron.log`; `ps aux \| grep cron` inside container | `docker compose up -d quant-hub`; run job manually |
| **Email not received** | `.env` SMTP vars; `docker exec quant-hub printenv EMAIL_TO` | Fix `.env` → `docker compose up -d --force-recreate quant-hub` |
| **Scan very slow / Yahoo errors** | `tail scan.log` for 429/404 | Use `--cache`; stagger cron; retry later |
| **`job_runs` status=failed** | `docker exec quant-hub-db psql -U quant -d quant_hub -c "SELECT job_name, error_message FROM job_runs ORDER BY started_at DESC LIMIT 3;"` | Fix root error in logs; rerun scan |
| **Universe change not reflected** | Edited repo path instead of bind mount? | Edit `/mnt/fast/quant-data/data/universes/` |
| **Container won't start** | `docker compose logs quant-hub --tail 100` | `docker compose build --no-cache quant-hub && docker compose up -d` |
| **Wrong tiers / scores after code change** | Old container image? | Rebuild image; optional rescan |

**Escalation SQL — recent failed jobs:**

```bash
docker exec quant-hub-db psql -U quant -d quant_hub -c \
  "SELECT job_name, status, error_message, started_at FROM job_runs ORDER BY started_at DESC LIMIT 5;"
```

**Escalation SQL — latest scans:**

```bash
docker exec quant-hub-db psql -U quant -d quant_hub -c \
  "SELECT scan_date, strategy_id, universe_id, actionable_count FROM scan_runs ORDER BY scan_time DESC LIMIT 10;"
```

More detail: [Runbook §9 Troubleshooting](RUNBOOK.md#9-troubleshooting) · [Emergency procedures](RUNBOOK.md#13-emergency-procedures).

---

## 8. Morning checklist (2 minutes)

| ✓ | Check | Command |
|---|-------|---------|
| ☐ | Containers running | `docker compose ps` |
| ☐ | DB healthy | `docker exec quant-hub quant-hub status` |
| ☐ | Cron log clean | `tail -50 /mnt/fast/quant-data/logs/cron.log` |
| ☐ | Latest breakout scan (weekdays) | Dashboard or `quant-hub status` |
| ☐ | Disk space OK | `df -h /mnt/fast/quant-data` |

---

## 9. What not to do

| Avoid | Why |
|-------|-----|
| `docker compose down -v` on production | Can destroy bind-mounted data if misconfigured |
| `scripts/full-rescan.sh` without approval | **Truncates all scan history** in Postgres |
| Expose `:5002` or `:5433` to the internet | No dashboard auth; default DB creds risk |
| Edit only repo `data/` and expect live change | Docker uses `/mnt/fast/quant-data/data/` |
| `docker compose restart` after `.env` change | Use `--force-recreate quant-hub` instead |

---

## 10. Document map

| Need | Read |
|------|------|
| **This guide** | Day-to-day ops, Docker, triage |
| [Runbook](RUNBOOK.md) | Full deploy, backup, upgrade, security |
| [User Manual](USER_MANUAL.md) | Dashboard for analysts |
| [Data Model](DATA_MODEL.md) | Postgres tables, caches, exports |
| [Architecture Gaps](ARCHITECTURE_GAPS.md) | Known monitoring/security gaps (lead ops) |
| Scanner docs | Breakout / Swing / Lynch scoring deep dives |

---

## Quick reference card

```bash
cd /opt/stacks/quant-hub
docker compose ps
docker exec quant-hub quant-hub status
tail -f /mnt/fast/quant-data/logs/cron.log
docker exec quant-hub quant-daily --universe sp500 --no-email
docker compose up -d --force-recreate quant-hub   # after .env change
docker compose up -d --build quant-hub          # after crontab/code change
docker compose restart quant-hub                  # quick app bounce
```

**Dashboard:** `http://<host>:5002`  
**Postgres (host):** `localhost:5433` / db `quant_hub` / user `quant`
