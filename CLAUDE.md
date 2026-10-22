# quant-hub

**Development stopped 2026-10-22: no edge found** (`docs/research/CONCLUSION.md`). Don't start
new feature work; any resumption starts with a pre-registered hypothesis in `docs/research/LOG.md`.

Homelab research stack, **Launchpad-only focus since 2026-10-22**: Launchpad (technical
scanner + ML). Lynch is switched off (no cron, hidden in the UI, code dormant); the sector
swing scanner was deleted after a backtest showed no edge (tag `archive/pre-launchpad-focus`).
Results in Postgres, served by a read-only
FastAPI (`src/quant_hub/api/`) to a React/Vite frontend (`frontend/`).
Research only — **not** a trading bot. Streamlit (`src/quant_hub/dashboard/`)
is being decommissioned: never add Streamlit UI, build in React.

## Hard rules

- **Everything runs in Docker.** The host has no Python deps; never run
  `python`/`pip`/`pytest`/`npm` on the host. Never `pip install`/`npm install`
  into a running container as the fix — change `pyproject.toml` /
  `frontend/package.json` / Dockerfile so a clean rebuild reproduces it.
- **Scoring is off-limits unless the user explicitly asks.** Don't modify
  `src/quant_hub/{scoring,factors,filters,regime,strategies,engine,lynch,report}/`
  or existing write methods in `infrastructure/postgres/repository.py`. Edits
  there trigger a permission prompt (`.claude/settings.json`); if one fires
  unexpectedly, stop and explain instead of approving around it. Run the
  `phase-scope-guard` skill before committing.
- **No fabricated trading numbers.** Entry/stop/target levels, position sizing,
  or anything a user might act on needs explicit user sign-off on the
  methodology first.
- Never read or print `.env.dev` / `.env.stage` / `.env.prod` (real SMTP
  credentials). Use the `*.example` files to learn the variable names.
- Don't add `plotly.js` to the frontend (unfixable critical transitive XSS
  via `maplibre-gl`). Run `npm audit` before adding any charting dependency.

## Research integrity

The point of this project is finding real edge, so every performance claim
must be evidence, not narrative.

- Measure signals with the `signal-eval` skill (tier vs same-universe
  forward return, t-stat over dates). Log every test, failures included, in
  `docs/research/LOG.md`.
- Run the `quant-skeptic` agent on any backtest, metric, or "this works"
  before reporting it or building on it.
- Under ~30 distinct dates or ~100 signals, the answer is "inconclusive".
- Known biases in this data: Yahoo-only daily bars, universes are today's
  members (survivorship), Lynch fundamentals are not point-in-time, no
  transaction costs anywhere yet. State which apply to any result.
- Don't build UI, position tracking, or digests on a signal that hasn't
  shown edge out-of-sample.
- Read-only DB queries:
  `docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' quant-hub-db-dev psql -U quant -d quant_hub`

## Dev stack

Always go through `scripts/run_env.sh` (sets compose project `quant-hub-dev`
and layers the right files). Bare `docker compose` infers project `quant-hub`
and silently targets nothing or creates orphan volumes.

```bash
./scripts/run_env.sh dev ps
./scripts/run_env.sh dev up -d --build --no-deps quant-hub quant-hub-api   # after Dockerfile/crontab/pyproject change
```

| Container | Role | Host port |
|---|---|---|
| `quant-hub-dev` | CLI, cron, Streamlit (legacy) | 5002 |
| `quant-hub-api-dev` | FastAPI, `--reload` | 5010 |
| `quant-hub-frontend-dev` | Vite dev server, proxies `/api` | 5020 |
| `quant-hub-db-dev` | Postgres | 5433 |

`src/` and `tests/` are bind-mounted into `quant-hub-dev`, so edits are live.
Containers run as root: anything that *creates* files in the repo from a
container needs `--user "$(id -u):$(id -g)"` (see `dev-stack` skill).
Cron runs 05:00–05:30 ET weekdays and 01:00–08:30 ET Saturday inside
`quant-hub-dev` (`docker/crontab` is authoritative) — avoid recreating the
container in those windows.

## Verify

```bash
docker exec quant-hub-dev pytest -q                            # backend; must not lose passes
docker exec quant-hub-dev ruff check /app/src/quant_hub/<path> # repo has pre-existing errors in forbidden paths — don't fix those
docker exec quant-hub-frontend-dev npx tsc -b                  # frontend has no unit tests
docker exec quant-hub-frontend-dev npm run lint                # 3 known warnings
curl -s http://localhost:5020/api/healthz                      # same path the UI uses
```

Don't run `npm run build` in the frontend container (writes root-owned
`dist/` into the repo). A PostToolUse hook runs ruff on every Python file you
edit and reports violations back.

## Code map

- `src/quant_hub/cli/` — console entry points (listed in `pyproject.toml`)
- `src/quant_hub/application/` — services; `infrastructure/postgres/` — repositories + `schema.sql`
- `src/quant_hub/strategies/launchpad/`, `scoring/`, `factors/` — the Launchpad rubric (protected; see Hard rules)
- `src/quant_hub/data/calendar.py` — NYSE sessions; the price cache requires the last completed session
- `src/quant_hub/api/` — read-only endpoints (contract: `docs/API_RUNBOOK.md`)
- `frontend/src/` — React 19 + react-router v7 + TanStack; `lib/` holds API types/helpers
- `tests/unit/` — pytest; `-m integration` tests need network and are skipped by default

## Git

- Trunk is `main`. One feature branch per phase/feature, merged to `main`
  after `phase-scope-guard` passes. (`dev` is stale — don't branch from it.)
- No CI exists; the container test run is the only regression gate.
- **Standing authorization (user, 2026-10-22): work autonomously end to end.**
  Commit, merge feature branches into `main`, and push to `origin` without
  asking — once `phase-scope-guard` passes and the tests are green. Make
  routine design calls yourself and record them in the commit or
  `docs/research/LOG.md`. Only stop for the hard rules above (scoring paths,
  trading numbers a user might act on), prod/stage, Phase 4, or spending money.
