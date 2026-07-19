# Quant Hub Run Team Quickstart

**Scope:** Launchpad + Lynch operations
**Last updated:** 2026-07-19

## Start here

```bash
cd /opt/stacks/quant-hub
docker compose ps
docker exec quant-hub quant-hub status
tail -50 /mnt/fast/quant-data/logs/cron.log
```

The dashboard is `http://<host>:5002`. Postgres is the system of record. The container reads live universe files from `/mnt/fast/quant-data/data/`, not repository `data/` files until they are copied there.

## Current commands

```bash
# Launchpad
docker exec quant-hub quant-launchpad --universe sp500_index --cache --report both
docker exec quant-hub quant-launchpad-daily --universe sp500_index --no-email
docker exec quant-hub quant-launchpad-all --cache --report both

# Lynch
docker exec quant-hub quant-lynch --universe sp500_index --no-email
docker exec quant-hub quant-lynch-all --no-email

# Supporting operations
docker exec quant-hub quant-universe list
docker exec quant-hub quant-universe refresh sp500_index
docker exec quant-hub quant-analytics weekly
docker exec quant-hub quant-digest daily
docker exec quant-hub quant-digest weekly --rebuild-analytics
```

## Saturday coverage

`docker/crontab` is authoritative and uses ET.

| Time | Coverage |
|---|---|
| 12:30 AM quarterly | Refresh `sp500_index` holdings |
| 1:30 AM | Launchpad across stock universes |
| 5:00 AM | Lynch across stock universes |
| 6:00 AM | Launchpad labels for recent `sp500_index` scans |
| 7:50 AM | Build weekly analytics |
| 8:00 AM | Send weekly Lynch digest with Launchpad ∩ Lynch overlap |

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
docker compose up -d --build quant-hub
docker exec quant-hub quant-hub init-db
docker exec quant-hub quant-hub status
```

Use `docker compose up -d --force-recreate quant-hub` after `.env` changes. See [Runbook](RUNBOOK.md) for backup, restore, and security procedures.
