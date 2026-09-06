# Quant Hub Run Team Quickstart

**Scope:** Launchpad + Lynch operations
**Last updated:** 2026-09-06

**Install / first boot:** [SETUP_GUIDE.md](SETUP_GUIDE.md).

Do not `cp .env.example .env` or run bare `docker compose up` / `docker compose ps`. Port **5002** and `/mnt/fast/quant-data` are **prod only**.

## Start here

```bash
cd /opt/stacks/quant-hub
./scripts/run_env.sh prod ps
docker exec quant-hub quant-hub status
tail -50 /mnt/fast/quant-data/logs/cron.log
```

Dev practice stack: `./scripts/run_env.sh dev ps` and `docker exec quant-hub-dev quant-hub status`.

**Prod** dashboard: `http://127.0.0.1:5002`. **Dev** dashboard: same port on a different stack (`quant-hub-dev`); do not run both if they share 5002. Postgres is the system of record. The **prod** container reads `/mnt/fast/quant-data/data/`, not repository `data/` files until they are copied there. Dev bind-mounts repo universe files.

## Current commands

```bash
# Prod container: quant-hub. Dev: quant-hub-dev. Weekday cron uses growth universes
# (see docker/crontab) — not a single 5:10 PM sp500_index job.
docker exec quant-hub quant-launchpad --universe most_actives --cache --report both
docker exec quant-hub quant-launchpad-daily --universe most_actives --no-email
docker exec quant-hub quant-launchpad-all --cache --report both

docker exec quant-hub quant-lynch --universe most_actives --no-email
docker exec quant-hub quant-lynch-all --no-email

# Supporting operations
docker exec quant-hub quant-universe list
docker exec quant-hub quant-universe refresh sp500_index
docker exec quant-hub quant-analytics weekly
docker exec quant-hub quant-digest daily
docker exec quant-hub quant-digest weekly --rebuild-analytics
```

## Saturday coverage

`docker/crontab` is authoritative (America/New_York). Older tables that listed a single 1:30 AM Launchpad-all and 5:00 AM Lynch-all are stale.

Current Saturday flow (see the crontab file): Launchpad-all in two waves (1:00 / 1:30 AM), staggered Lynch-all (2:30–5:30 AM), ML labels (~7:00 AM), weekly analytics (8:15 AM), weekly digest (8:30 AM).

If Saturday jobs fail, run the missed command in schedule order. After both product scans, run `quant-analytics weekly`, then rebuild/send the weekly digest if needed.

## Triage

| Problem | First action |
|---|---|
| Dashboard says no scan | Check selected product/universe/date; run `quant-launchpad` or `quant-lynch` |
| Cron missing | Check `cron.log` and `docker exec quant-hub ps aux \| grep cron` |
| Yahoo rate limiting | Avoid parallel manual scans, use `--cache`, retry later |
| Lynch candidate has blank score | Treat as data retrieval failure; rerun the universe later |
| Weekly overlap missing | Confirm both Saturday product runs and rerun `quant-analytics weekly` |
| Labels incomplete | Run `quant-ml warm-cache`, then rerun `quant-ml label --strategy launchpad` |

## Deploy changes

```bash
cd /opt/stacks/quant-hub
./scripts/run_env.sh prod up --build -d
docker exec quant-hub quant-hub init-db
docker exec quant-hub quant-hub status
```

After `.env.prod` changes: `./scripts/run_env.sh prod up -d --force-recreate`. See [Runbook](RUNBOOK.md) for backup, restore, and security.
