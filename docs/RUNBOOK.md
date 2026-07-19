# Quant Hub Administrator Runbook

**Product scope:** Launchpad technical scanning + ML and Lynch fundamentals
**Install path:** `/opt/stacks/quant-hub`  
**Last updated:** 2026-07-19

## System overview

`quant-hub` runs the Streamlit dashboard, cron, and product CLIs. `quant-hub-db` is PostgreSQL 16 and is the system of record. The dashboard is exposed on host port 5002 and Postgres on 5433.

Persistent host paths:

| Path | Purpose |
|---|---|
| `/mnt/fast/quant-data/postgres` | PostgreSQL data |
| `/mnt/fast/quant-data/data` | Universes, price cache, exports, ML artifacts |
| `/mnt/fast/quant-data/logs` | Cron, application, and dashboard logs |

All timestamps in `docker/crontab` are America/New_York. `docker/crontab` is the source of truth; `docker/jobs.yaml` is its reference mirror.

## Deploy and verify

```bash
cd /opt/stacks/quant-hub
cp .env.example .env
docker compose up -d --build
docker compose ps
docker exec quant-hub quant-hub init-db
docker exec quant-hub quant-hub status
```

Set a strong `POSTGRES_PASSWORD` and a matching `DATABASE_URL`. Configure `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, and `EMAIL_TO` for digests. Do not commit `.env`.

Test current products:

```bash
docker exec quant-hub quant-launchpad --universe sp500_index --cache --report both
docker exec quant-hub quant-lynch --universe sp500_index --no-email
```

Open `http://<host>:5002` and verify Command Center, Digest, Launchpad, and Lynch load.

## Current schedule

Do not infer schedules from old documentation. Verify the installed cron file after deployments:

```bash
docker exec quant-hub cat /etc/cron.d/quant-hub
```

| When (ET) | Command |
|---|---|
| Mon–Fri 5:10 PM | `quant-launchpad-daily --universe sp500_index --no-email` |
| Mon–Fri 5:35 PM | `quant-digest daily` |
| First Sat of Jan/Apr/Jul/Oct, 12:30 AM | `quant-universe refresh sp500_index` |
| Saturday 1:30 AM | `quant-launchpad-all --cache --report both` |
| Saturday 5:00 AM | `quant-lynch-all --no-email` |
| Saturday 6:00 AM | `quant-ml label --strategy launchpad --universe sp500_index --since <90d>` |
| Saturday 7:50 AM | `quant-analytics weekly` |
| Saturday 8:00 AM | `quant-digest weekly` |

Scheduled scans persist results without email. Digest commands send mail. The weekly digest uses Launchpad ∩ Lynch overlap as the combined signal.

## Daily operations

```bash
docker compose ps
docker exec quant-hub quant-hub status
tail -100 /mnt/fast/quant-data/logs/cron.log
docker exec quant-hub quant-hub report --strategy launchpad --universe sp500_index
docker exec quant-hub quant-hub report --strategy lynch --universe sp500_index
```

Current manual recovery commands:

```bash
docker exec quant-hub quant-launchpad-daily --universe sp500_index --no-email
docker exec quant-hub quant-launchpad-all --cache --report both
docker exec quant-hub quant-lynch --universe sp500_index --no-email
docker exec quant-hub quant-lynch-all --no-email
docker exec quant-hub quant-analytics weekly
docker exec quant-hub quant-digest weekly --rebuild-analytics
```

Same-day reruns safely replace the run for a product/universe/date.

## Universe operations

The repository contains versioned copies, but the running container reads `/mnt/fast/quant-data/data/`.

```bash
docker exec quant-hub quant-universe list
docker exec quant-hub quant-universe show sp500_index
docker exec quant-hub quant-universe refresh sp500_index
```

After changing repository universe files, copy `universes.json` and the relevant ticker file to the live data mount, then verify with `quant-universe show`.

Launchpad and Lynch batch commands operate on stock universes. ETF-mode universes are skipped by Launchpad.

## ML operations

Launchpad is the only ML workflow. Its runbook is [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md). The essential progression is:

```bash
docker exec quant-hub quant-backfill launchpad --universe mega_runners --since 2021-07-29
docker exec quant-hub quant-ml warm-cache --universe mega_runners
docker exec quant-hub quant-ml label --strategy launchpad --universe mega_runners --since 2021-07-29
docker exec quant-hub quant-ml train --strategy launchpad --universe mega_runners --since 2021-07-29 --horizon 20
```

Back up Postgres before broad backfills. Never truncate `scan_runs` on the ML database; labels cascade with their parent runs.

## Monitoring and troubleshooting

| Symptom | Checks | Recovery |
|---|---|---|
| Database unreachable | `docker compose ps`; `docker compose logs quant-hub-db --tail 50` | Start the DB; validate `.env` and host/container DSNs |
| Dashboard has no scan | `quant-hub status`; selected product/universe/date | Run `quant-launchpad` or `quant-lynch` for the needed universe |
| Cron missed a run | `ps aux \| grep cron`; `cron.log`; installed crontab | Restart `quant-hub`, then run the exact missed command manually |
| Slow scan or Yahoo errors | `scan.log` and `cron.log` for 429/404 | Use `--cache`, avoid overlapping manual runs, retry later |
| Lynch scores missing | `job_runs`, logs, per-ticker detail | Retry the affected universe later; missing is not zero |
| Weekly digest lacks overlap | Confirm Saturday Launchpad and Lynch runs; execute `quant-analytics weekly` | Rebuild analytics, then `quant-digest weekly --rebuild-analytics` |
| Labels incomplete | `quant-ml status` | Warm cache and rerun labels; recent runs need future bars |

Inspect jobs directly:

```bash
docker exec quant-hub-db psql -U quant -d quant_hub -c \
  "SELECT job_name,status,error_message,started_at FROM job_runs ORDER BY started_at DESC LIMIT 10;"
```

## Backups and maintenance

```bash
mkdir -p /mnt/fast/quant-data/backups
docker exec quant-hub-db pg_dump -U quant quant_hub \
  | gzip > /mnt/fast/quant-data/backups/quant_hub_$(date +%Y%m%d).sql.gz
```

After code, dependency, Dockerfile, or crontab changes:

```bash
cd /opt/stacks/quant-hub
docker compose up -d --build quant-hub
docker exec quant-hub quant-hub init-db
docker exec quant-hub quant-hub status
```

After `.env` changes, recreate rather than merely restart:

```bash
docker compose up -d --force-recreate quant-hub
```

## Security baseline

- Keep dashboard and Postgres on a trusted network; the dashboard has no built-in authentication.
- Firewall or remove host access to Postgres if host-side tools do not require it.
- Use strong database and SMTP credentials.
- Do not expose `.env`, cron environment files, backups, or exports.

See [Architecture Gaps](ARCHITECTURE_GAPS.md) for tracked platform and security gaps.
