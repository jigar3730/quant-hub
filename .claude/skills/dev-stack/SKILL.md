---
name: dev-stack
description: Launch, check, rebuild, and verify the quant-hub dev stack (Postgres, FastAPI, Vite frontend, cron/CLI container) via Docker Compose. Use whenever you need to run the app, confirm a frontend or API change works, install a dependency, rebuild after a Dockerfile/crontab/pyproject change, or smoke-test an endpoint. Covers the "launching the app" step for /run in this repo.
---

# quant-hub dev stack

CLAUDE.md has the container table and basic verify commands. This skill covers
the less common operations.

## Always use run_env.sh

`./scripts/run_env.sh dev <compose args>` sets `COMPOSE_PROJECT_NAME=quant-hub-dev`
and layers `docker-compose.yml` + `docker-compose.dev.yml` with `.env.dev`.
Never call `docker compose` directly for this stack — it infers project
`quant-hub`, silently no-ops on stop/rm, and creates orphan volumes.

Check state before starting anything; peer sessions may already have it up:

```bash
./scripts/run_env.sh dev ps
```

If containers are running, `docker exec` into them — don't restart the stack.

## What needs what after a change

| Changed | Action |
|---|---|
| `src/**`, `tests/**` | nothing — bind-mounted; API auto-reloads |
| `frontend/src/**` | nothing — Vite HMR |
| `pyproject.toml` deps/scripts, `docker/Dockerfile`, `docker/crontab` | `./scripts/run_env.sh dev up -d --build --no-deps quant-hub quant-hub-api` |
| `docker-compose*.yml` | `./scripts/run_env.sh dev up -d --no-deps <service>` |
| `docker/Dockerfile.frontend` (e.g. Node bump) | see "Frontend base-image change" |

Avoid recreating `quant-hub-dev` during cron windows (weekdays 05:00–05:30 ET,
Saturday 01:00–08:30 ET).

## Writing into the repo from a container

Containers run as root. Anything that creates files under a bind mount
(`npm install`, scaffolding, codegen) must map the host UID:

```bash
./scripts/run_env.sh dev run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp quant-hub-frontend <cmd>
```

Shortcut for a one-off frontend dependency (node_modules is a named volume, so
root there is harmless) — then hand back the two bind-mounted files:

```bash
docker exec quant-hub-frontend-dev npm install <package>
docker exec quant-hub-frontend-dev npm audit --omit=dev
docker exec quant-hub-frontend-dev chown "$(id -u):$(id -g)" /app/package.json /app/package-lock.json
```

If you hit `EACCES` from earlier root-owned files, fix it from a root
container (`docker exec <ctr> chown -R <uid>:<gid> <path>`), not host `sudo`.

## Frontend base-image change

`node_modules` is a named volume that shadows the image's own install, so a
rebuild alone keeps the stale modules:

```bash
./scripts/run_env.sh dev rm -sf quant-hub-frontend
docker volume rm quant-hub-dev_quant-hub-frontend-node-modules
./scripts/run_env.sh dev up -d --build --no-deps quant-hub-frontend
docker exec quant-hub-frontend-dev node --version
```

## Smoke-testing through the API

Curl through the frontend proxy (port 5020) so you exercise the UI's path:

```bash
curl -s http://localhost:5020/api/healthz
curl -s "http://localhost:5020/api/scans/latest?strategy_id=launchpad&universe_id=<id>"
curl -s "http://localhost:5020/api/scans/<run_id>/report"
```

Full endpoint contract: `docs/API_RUNBOOK.md`.

## Running a scanner by hand

```bash
docker exec -e LOG_LEVEL=INFO quant-hub-dev quant-sector-swing
docker exec quant-hub-dev quant-launchpad --tickers NVDA --cache --report json
```

The container defaults to `LOG_LEVEL=WARNING`; pass `-e LOG_LEVEL=INFO` to see
scan progress. Use `docker exec -i` when piping a script on stdin.

## Runtime-checking React components

There's no frontend test runner. Beyond `tsc -b` + lint, you can SSR-render a
component via Vite's `ssrLoadModule` in the container (put the script in `/tmp`
inside the container, not the repo). Don't run `npm run build` in the container
— it writes root-owned `dist/` into the repo.
