# Quant Hub

Homelab quant stack focused on **Launchpad** (quality coiled-spring scanner + ML) and **Lynch** (fundamental screen). Postgres-backed results, parquet price cache, Streamlit dashboard, and digest emails.

## Which stack am I on?

This **dev** branch's `docker-compose.yml` is the **sandbox**. It does not share data with production.

| | Production | Dev (this branch) |
|---|---|---|
| Containers | `quant-hub`, `quant-hub-db` | `quant-hub-dev`, `quant-hub-db-dev` |
| Dashboard | `:5002` | `:5003` |
| Postgres (host) | `127.0.0.1:5433` | `127.0.0.1:5434` |
| Volumes | `/mnt/fast/quant-data/{data,logs,postgres}` | `/mnt/fast/quant-data/{data-dev,logs-dev,postgres-dev}` |

Learn ML here: [ML Operations Course](docs/ML_OPERATIONS.md). Leave production scanners on the other stack.

## Quick start (dev)

```bash
cd /opt/stacks/quant-hub
cp .env.example .env   # set POSTGRES_PASSWORD; host DATABASE_URL port is 5434
docker compose up -d --build
mkdir -p /mnt/fast/quant-data/data-dev
cp data/universes.json /mnt/fast/quant-data/data-dev/
cp -r data/universes /mnt/fast/quant-data/data-dev/
docker exec quant-hub-dev quant-hub status
```

Dashboard: `http://<host>:5003`.

Manual scans:

```bash
docker exec quant-hub-dev quant-launchpad --universe mega_runners --cache --report both
docker exec quant-hub-dev quant-launchpad-all --cache --report both
docker exec quant-hub-dev quant-lynch --universe sp500_index --no-email
```

## CLI

| Command | Purpose |
|---------|---------|
| `quant-launchpad` | Single-universe Launchpad scan |
| `quant-launchpad-daily` | Weekday Launchpad workflow |
| `quant-launchpad-all` | Launchpad across stock-mode universes |
| `quant-lynch` / `quant-lynch-all` | Lynch fundamental screen |
| `quant-backfill launchpad` | Point-in-time Saturday backfill for ML |
| `quant-ml` | warm-cache / label / export / train / evaluate / models |
| `quant-digest` | Daily Launchpad + weekly Lynch emails |
| `quant-hub` | status, init-db, cleanup, report, ticker history/show |
| `quant-universe` | list / show / refresh universes |
| `quant-analytics` | weekly digest analytics payload |
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
| [ML Operations Course](docs/ML_OPERATIONS.md) | Learn ML + MLOps hands-on with this pipeline |
| [ML Ops](docs/ML_OPS.md) | Label / train / evaluate (short) |
| [Analytics Guide](docs/ANALYTICS_GUIDE.md) | Weekly analytics payload |
| [Data Model](docs/DATA_MODEL.md) | PostgreSQL and JSONB model |
| [ML Foundation](docs/ML_FOUNDATION.md) | ML design and safeguards |
| [Junior Developer Database Guide](docs/JUNIOR_DEV_DATABASE_GUIDE.md) | Database workflows |
| [Run Team Quickstart](docs/RUN_TEAM_QUICKSTART.md) | Team operating checklist |
| [Architecture Gaps](docs/ARCHITECTURE_GAPS.md) | Current risks and remediation |

## Layout

```
src/quant_hub/     application code (launchpad + lynch)
data/universes/    ticker lists (sync to /mnt/fast/quant-data/data-dev on this branch)
docker/            Dockerfile, crontab, entrypoint
docs/              operator manuals
scripts/           launchpad-lynch-rescan.sh
```

## Schedule (America/New_York)

See `docker/crontab`: Launchpad daily, Launchpad-all Saturday, Lynch-all Saturday, Launchpad ML labels, digests.
