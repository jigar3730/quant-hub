---
name: dev-stack
description: Launch, check, and verify the quant-hub dev stack (Postgres, Phase 1 API, Phase 2 frontend) via Docker Compose. Use this whenever you need to run the app, confirm a frontend or API change works, typecheck/lint the frontend, or smoke-test an endpoint — instead of guessing docker compose invocations from scratch. Covers the "launching the app" step for /run in this repo.
---

# quant-hub dev stack

Everything in this project runs in Docker — never start Postgres, the API, or the
frontend dev server directly on the host (see the containerize-everything rule
in project memory). This skill is the reference for doing that correctly.

## Compose invocation

Always use the dev env file with both compose files layered, exactly like the
Makefile does:

```bash
docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml <cmd>
```

`make dev-up` runs this with `up --build` in the foreground. For a background
check/verify pass, prefer:

```bash
docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up -d
```

**Check what's already running first** — `docker ps -a --filter name=quant-hub`.
Another session (this repo has peer Claude Code sessions) may already have the
stack up under these container names, and a second `up`/`run` against the same
names will fail with "Container name already in use". If they're already
running, just `docker exec` into them — don't restart the stack.

| Container | Service | Port (host) |
|---|---|---|
| `quant-hub-db-dev` | Postgres | `${POSTGRES_PORT:-5433}` |
| `quant-hub-dev` | Streamlit dashboard | `${DASHBOARD_PORT:-5002}` |
| `quant-hub-api-dev` | Phase 1 FastAPI (read-only) | `${API_PORT:-5010}` |
| `quant-hub-frontend-dev` | Phase 2 Vite dev server | `${FRONTEND_PORT:-5020}` |

The frontend container proxies `/api/*` to `quant-hub-api:8000` internally
(see `frontend/vite.config.ts`), so hitting `http://localhost:5020/api/...`
from the host exercises the exact same path the React app uses.

## Typecheck & lint the frontend

Safe to run as the container's default user — these only write to the
`quant-hub-frontend-node-modules` named volume, not the bind-mounted
`./frontend` directory, so there's no host-ownership risk:

```bash
docker exec quant-hub-frontend-dev npx tsc -b
docker exec quant-hub-frontend-dev npm run lint
```

## When a command writes into the bind-mounted repo

Anything that scaffolds or installs into `./frontend` itself (not just the
named `node_modules` volume) — `npm install`, `npm create`, codegen — must map
the host UID/GID or the files come out root-owned and unwritable from the
host:

```bash
docker compose --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml \
  run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp quant-hub-frontend <cmd>
```

If you hit `EACCES` on a bind-mounted path because a prior container already
left root-owned files, fix it with a root container chowning its own mount —
not host-side `sudo chown` (see the docker-uid-mapping project memory).

## Smoke-test real data through the API

Prefer curling through the frontend's proxy port so you're validating the
same path the UI takes:

```bash
curl -s "http://localhost:5020/api/scans/latest?strategy_id=launchpad&universe_id=<id>"
curl -s "http://localhost:5020/api/scans/<run_id>/report"
```

Other read-only endpoints: `/scans`, `/tickers/{ticker}/history`,
`/command-center`, `/outcomes`, `/outcomes/status`, `/models`, `/healthz`
(full contract in `docs/API_RUNBOOK.md`).

## Backend Python tests

The FastAPI/CLI/scoring test suite runs the same way — see the
`phase-scope-guard` skill for when and why to run it during modernization work:

```bash
docker exec quant-hub-dev pytest -q
```
