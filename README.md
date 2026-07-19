# Quant Hub

Homelab quant stack focused on **Launchpad** (quality coiled-spring scanner + ML) and **Lynch** (fundamental screen). Postgres-backed results, parquet price cache, Streamlit dashboard, and digest emails.

## Quick start

```bash
cd /opt/stacks/quant-hub
cp .env.example .env   # set POSTGRES_PASSWORD, DATABASE_URL, SMTP_*
docker compose up -d --build
docker exec quant-hub quant-hub status
```

Manual scans (inside container):

```bash
docker exec quant-hub quant-launchpad --universe mega_runners --cache --report both
docker exec quant-hub quant-launchpad-all --cache --report both
docker exec quant-hub quant-lynch --universe sp500_index --no-email
docker exec quant-hub quant-lynch-all --no-email
docker exec quant-hub bash /app/scripts/launchpad-lynch-rescan.sh
```

Dashboard: `http://<host>:5002` (`quant-view` inside the container).

## CLI

| Command | Purpose |
|---------|---------|
| `quant-launchpad` | Single-universe Launchpad scan |
| `quant-launchpad-daily` | Weekday Launchpad workflow |
| `quant-launchpad-all` | Launchpad across stock-mode universes |
| `quant-lynch` / `quant-lynch-all` | Lynch fundamental screen |
| `quant-backfill launchpad` | Point-in-time Saturday backfill for ML |
| `quant-ml` | warm-cache / label / export / train / evaluate |
| `quant-digest` | Daily Launchpad + weekly Lynch emails |
| `quant-hub` | status, init-db, report, history |
| `quant-universe` | list / show / refresh universes |
| `quant-view` | Streamlit dashboard |

## Docs

| Doc | Audience |
|-----|----------|
| [Launchpad ML Guide](docs/LAUNCHPAD_ML_GUIDE.md) | mega_runners → backfill → ML → tune |
| [Launchpad Scanner](docs/LAUNCHPAD_SCANNER.md) | Scoring and tiers |
| [Lynch Scanner](docs/LYNCH_SCANNER.md) | Fundamental screen |
| [Digest Policy](docs/DIGEST_POLICY.md) | Email content rules |
| [Runbook](docs/RUNBOOK.md) | Ops / cron / recover |
| [User Manual](docs/USER_MANUAL.md) | Dashboard and daily workflow |
| [ML Ops](docs/ML_OPS.md) | Label / train / evaluate |

## Layout

```
src/quant_hub/     application code (launchpad + lynch)
data/universes/    ticker lists (sync to /mnt/fast/quant-data/data on the host)
docker/            Dockerfile, crontab, entrypoint
docs/              operator manuals
scripts/           launchpad-lynch-rescan.sh
```

## Schedule (America/New_York)

See `docker/crontab`: Launchpad daily, Launchpad-all Saturday, Lynch-all Saturday, Launchpad ML labels, digests.
