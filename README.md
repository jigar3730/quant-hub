# Quant Hub

**Install here:** [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md)

**Do not do these three things** (they start an empty or colliding stack):

1. Do not run `cp .env.example .env` then `docker compose up`.
2. Do not run bare `docker compose ps` / `up` against `docker-compose.yml` alone (it has **no volumes**).
3. Port **5002** + `/mnt/fast/quant-data` is strictly **prod**, not every environment.

Homelab research stack for **Launchpad** (quality coiled-spring scanner + ML) and **Lynch** (fundamental screen). Results live in Postgres. You view them in a Streamlit dashboard and optional digest emails. This is **not** a trading bot.

## First-time setup

Follow [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md) only. Short version after its prerequisites:

```bash
cd /opt/stacks/quant-hub
cp .env.dev.example .env.dev    # edit POSTGRES_PASSWORD in both places
./scripts/run_env.sh dev up --build -d
docker exec quant-hub-dev quant-hub status
```

Dashboard (dev): `http://127.0.0.1:5002`

| Environment | Start | App container | Dashboard |
|-------------|--------|---------------|-----------|
| Practice (**dev**) | `./scripts/run_env.sh dev up --build -d` | `quant-hub-dev` | port 5002 |
| Dress rehearsal (**stage**) | `./scripts/run_env.sh stage up -d` | `quant-hub-stage` | port 5003 |
| Live (**prod**) | `./scripts/run_env.sh prod up -d` | `quant-hub` | port 5002 (localhost only) |

Always pair `docker-compose.yml` with `docker-compose.<env>.yml` via `run_env.sh`. The base file alone has no data volumes.

## After it is running

```bash
# Dev examples — use quant-hub / quant-hub-stage in prod / stage
docker exec quant-hub-dev quant-launchpad --tickers NVDA --cache --report json
docker exec quant-hub-dev quant-universe list
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
| [Setup Guide](docs/SETUP_GUIDE.md) | **Start here** — Docker, env files, dev vs prod |
| [User Manual](docs/USER_MANUAL.md) | Dashboard and daily workflow |
| [Launchpad Scanner](docs/LAUNCHPAD_SCANNER.md) | Scoring and tiers |
| [Lynch Scanner](docs/LYNCH_SCANNER.md) | Fundamental screen |
| [Launchpad ML Guide](docs/LAUNCHPAD_ML_GUIDE.md) | mega_runners → backfill → ML → tune |
| [ML Operations Course](docs/ML_OPERATIONS.md) | Learn ML + MLOps on this pipeline |
| [ML Ops](docs/ML_OPS.md) | Label / train / evaluate (short) |
| [ML Foundation](docs/ML_FOUNDATION.md) | ML design and safeguards |
| [Digest Policy](docs/DIGEST_POLICY.md) | Email content rules |
| [Analytics Guide](docs/ANALYTICS_GUIDE.md) | Weekly analytics payload |
| [Data Model](docs/DATA_MODEL.md) | PostgreSQL and JSONB model |
| [Runbook](docs/RUNBOOK.md) | Ops / cron / recover |
| [Run Team Quickstart](docs/RUN_TEAM_QUICKSTART.md) | Team operating checklist |
| [Junior Developer Database Guide](docs/JUNIOR_DEV_DATABASE_GUIDE.md) | Database workflows |
| [Architecture Gaps](docs/ARCHITECTURE_GAPS.md) | Current risks and remediation |
| [Modernization Audit](docs/MODERNIZATION_AUDIT.md) | API decoupling plan and frontend migration roadmap |

## Layout

```
src/quant_hub/           application code
data/universes/          ticker lists (prod: also copy to /mnt/fast/quant-data/data)
docker/                  Dockerfile, crontab, entrypoint
docker-compose.yml       shared services (use with an override)
docker-compose.*.yml     dev / stage / prod
docs/SETUP_GUIDE.md      first-time setup
scripts/run_env.sh       start/stop an environment
```

## Schedule (America/New_York)

`docker/crontab` is authoritative. Weekday Launchpad on growth universes, Saturday coverage + Lynch + ML labels + weekly digest. Do not copy times from older manuals.
