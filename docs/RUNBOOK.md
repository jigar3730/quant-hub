# Quant Hub Administrator Runbook

**Product scope:** Launchpad technical scanning + ML and Lynch fundamentals
**Install path:** `/opt/stacks/quant-hub`  
**Last updated:** 2026-09-06

**First-time install:** [SETUP_GUIDE.md](SETUP_GUIDE.md). Status and deploy: `./scripts/run_env.sh {dev|stage|prod}`. Do not `cp .env.example .env` or run bare `docker compose up` / `ps`. Port 5002 and `/mnt/fast/quant-data` are **prod**.

## System overview

`quant-hub` (prod container name) runs the Streamlit dashboard, cron, and product CLIs. `quant-hub-db` is PostgreSQL 16 and is the system of record. Dev uses `quant-hub-dev` / `quant-hub-db-dev`. The prod dashboard is `127.0.0.1:5002` and Postgres `127.0.0.1:5433`.

Persistent host paths (**prod** only — dev uses Docker volumes; stage uses `/mnt/fast/quant-data-stage/`):

| Path | Purpose |
|---|---|
| `/mnt/fast/quant-data/postgres` | PostgreSQL data |
| `/mnt/fast/quant-data/data` | Universes, price cache, exports, ML artifacts |
| `/mnt/fast/quant-data/logs` | Cron, application, and dashboard logs |

All timestamps in `docker/crontab` are America/New_York. `docker/crontab` is the source of truth; `docker/jobs.yaml` is its reference mirror.

## Deploy and verify

```bash
cd /opt/stacks/quant-hub
cp .env.prod.example .env.prod   # or .env.dev.example → .env.dev for practice
# Edit POSTGRES_PASSWORD in both the password line and DATABASE_URL
./scripts/run_env.sh prod up --build -d
./scripts/run_env.sh prod ps
docker exec quant-hub quant-hub status
```

Dev: `./scripts/run_env.sh dev up --build -d` then `docker exec quant-hub-dev quant-hub status`.

Set a strong `POSTGRES_PASSWORD` and a matching `DATABASE_URL`. Configure `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, and `EMAIL_TO` for digests. Do not commit `.env.prod` or `.env.dev`.

Test current products:

```bash
# Prod: quant-hub. Dev: quant-hub-dev. Cron universes: docker/crontab (not a 5:10 PM sp500_index slot).
docker exec quant-hub quant-launchpad --universe most_actives --cache --report both
docker exec quant-hub quant-lynch --universe most_actives --no-email
```

Open the **prod** dashboard at `http://127.0.0.1:5002` (dev also uses 5002 on a separate stack — do not run both at once). Verify Command Center, Digest, Launchpad, and Lynch load.

## Current schedule

`docker/crontab` is the source of truth. Do not copy weekday `sp500_index` times from older manuals. Verify after deploy:

```bash
docker exec quant-hub cat /etc/cron.d/quant-hub
```

Weekday (ET): Launchpad on `most_actives`, `large_cap_growth`, `small_cap_growth`, `mid_cap_growth` (5:10–5:25 PM), then `quant-digest daily` at 5:40 PM. Saturday: Launchpad-all, staggered Lynch-all, ML labels, analytics, weekly digest.

Scheduled scans persist results without email. Digest commands send mail. The weekly digest uses Launchpad ∩ Lynch overlap as the combined signal.

## Daily operations

```bash
./scripts/run_env.sh prod ps
docker exec quant-hub quant-hub status
tail -100 /mnt/fast/quant-data/logs/cron.log
docker exec quant-hub quant-hub report --strategy launchpad --universe most_actives
docker exec quant-hub quant-hub report --strategy lynch --universe most_actives
```

Current manual recovery commands (match `docker/crontab`; prod container `quant-hub`):

```bash
docker exec quant-hub quant-launchpad-daily --universe most_actives --no-email
docker exec quant-hub quant-launchpad-all --cache --report both
docker exec quant-hub quant-lynch --universe most_actives --no-email
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
docker exec quant-hub quant-backfill launchpad --universe mega_runners --since YYYY-MM-DD
docker exec quant-hub quant-ml warm-cache --universe mega_runners
docker exec quant-hub quant-ml label --strategy launchpad --universe mega_runners --since YYYY-MM-DD
docker exec quant-hub quant-ml train --strategy launchpad --universe mega_runners --since YYYY-MM-DD --horizon 20
```

Back up Postgres before broad backfills. Never truncate `scan_runs` on the ML database; labels cascade with their parent runs.

## Monitoring and troubleshooting

| Symptom | Checks | Recovery |
|---|---|---|
| Database unreachable | `./scripts/run_env.sh prod ps`; `./scripts/run_env.sh prod logs postgres --tail 50` | Start with `run_env.sh`; validate `.env.prod` (dev: `.env.dev` / `quant-hub-db-dev`) |
| Dashboard has no scan | `quant-hub status`; selected product/universe/date | Run `quant-launchpad` or `quant-lynch` for the needed universe |
| Cron missed a run | `ps aux \| grep cron`; `cron.log`; installed crontab | Restart `quant-hub`, then run the exact missed command manually |
| Slow scan or Yahoo errors | `scan.log` and `cron.log` for 429/404 | Use `--cache`, avoid overlapping manual runs, retry later |
| Lynch scores missing | `job_runs`, logs, per-ticker detail | Retry the affected universe later; missing is not zero |
| Weekly digest lacks overlap | Confirm Saturday Launchpad and Lynch runs; execute `quant-analytics weekly` | Rebuild analytics, then `quant-digest weekly --rebuild-analytics` |
| Labels incomplete | `quant-ml status` | Warm cache and rerun labels; recent runs need future bars |

Inspect jobs directly (prod names; dev: `quant-hub-db-dev` / `quant_hub_dev`):

```bash
docker exec quant-hub-db psql -U quant -d quant_hub -c \
  "SELECT job_name,status,error_message,started_at FROM job_runs ORDER BY started_at DESC LIMIT 10;"
```

## Backups and maintenance

`/mnt/fast/quant-data` is the **prod** data root. Dev does not use this path.

```bash
mkdir -p /mnt/fast/quant-data/backups
docker exec quant-hub-db pg_dump -U quant quant_hub \
  | gzip > /mnt/fast/quant-data/backups/quant_hub_$(date +%Y%m%d).sql.gz
```

After code, dependency, Dockerfile, or crontab changes:

```bash
cd /opt/stacks/quant-hub
./scripts/run_env.sh prod up --build -d
docker exec quant-hub quant-hub init-db
docker exec quant-hub quant-hub status
```

After `.env.prod` changes, recreate rather than merely restart:

```bash
./scripts/run_env.sh prod up -d --force-recreate
```

## Security baseline

- Keep dashboard and Postgres on a trusted network; the dashboard has no built-in authentication.
- Firewall or remove host access to Postgres if host-side tools do not require it.
- Use strong database and SMTP credentials.
- Do not expose `.env.prod`, `.env.dev`, cron environment files, backups, or exports.

See [Architecture Gaps](ARCHITECTURE_GAPS.md) for tracked platform and security gaps.
