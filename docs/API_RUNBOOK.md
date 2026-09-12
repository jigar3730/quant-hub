# Quant Hub API — Testing Runbook

Read-only companion API to the Streamlit dashboard (Phase 1 of
`docs/MODERNIZATION_AUDIT.md`). It serves the same Postgres data through the
same repositories as the dashboard — it never writes to the database and
never recomputes a score. Source: `src/quant_hub/api/`.

This runbook documents the API **as implemented today**. It does not add,
change, or assume any behavior beyond what is in the code.

---

## 1. Environment Setup

The API ships as the `quant-hub-api` compose service, built from the same
image as the dashboard, started via `scripts/run_env.sh`.

```bash
# Start (or confirm running) the dev stack — postgres, dashboard, api
./scripts/run_env.sh dev up -d

# Confirm containers are up and healthy
docker ps --filter "name=quant-hub" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### Ports by environment

Defaults come from `docker-compose.yml` + the per-env overlay
(`docker-compose.dev.yml` / `.stage.yml` / `.prod.yml`) and `.env.<env>`.

| Service | Container name (dev) | Host port (default) | Container port |
|---|---|---|---|
| API (FastAPI/uvicorn) | `quant-hub-api-dev` | `${API_PORT:-5010}` | 8000 |
| Dashboard (Streamlit) | `quant-hub-dev` | `${DASHBOARD_PORT:-5002}` | 5000 |
| Postgres | `quant-hub-db-dev` | `127.0.0.1:${POSTGRES_PORT:-5433}` | 5432 |

Prod/stage container names drop/replace the `-dev` suffix
(`quant-hub-api`, `quant-hub`, `quant-hub-db` for prod;
`*-stage` for stage) — see `docker-compose.prod.yml` / `.stage.yml`.

> Only `dev`'s API/dashboard ports are open on all interfaces; prod/stage
> bind `127.0.0.1` only (see the `ports:` blocks in those overlay files) —
> test those from the host itself or over a tunnel, not remotely.

### Health check

```bash
# Base URL for the rest of this doc (adjust host/port for your env)
BASE_URL="http://localhost:5010"

curl -s "$BASE_URL/healthz" | jq .
```

Expected (DB reachable):
```json
{ "status": "ok", "database": true }
```

If Postgres is unreachable, the endpoint still returns **200** with a
degraded body (it does not fail the HTTP call) — this is the intended
behavior in `app.py`:
```json
{ "status": "degraded", "database": false }
```

### Interactive docs

FastAPI auto-generates these — useful for exploring schemas without reading
source:

```bash
open "$BASE_URL/docs"       # Swagger UI
open "$BASE_URL/openapi.json"
```

---

## 2. Endpoint Testing Catalog

General notes that apply to every endpoint below:

- All routes are **GET only** — this is a read-only API; there are no
  POST/PUT/PATCH/DELETE routes in `src/quant_hub/api/routers/`.
- Malformed query parameters (e.g. `since=not-a-date`, non-integer `run_id`)
  are rejected by FastAPI/Pydantic before the route body runs, returning
  **422 Unprocessable Entity** with a `detail` array — not 400. Where a
  route explicitly raises an error, it's called out below; otherwise assume
  422-on-bad-input and no other explicit error path.

### 2.1 `GET /healthz`

Liveness + DB connectivity probe.

| Param | Type | Location | Required | Notes |
|---|---|---|---|---|
| — | — | — | — | no parameters |

```bash
curl -s "$BASE_URL/healthz"
```

200 OK:
```json
{ "status": "ok", "database": true }
```
Degraded (still 200, DB down):
```json
{ "status": "degraded", "database": false }
```
No 4xx path — this route has no inputs and no `HTTPException`.

---

### 2.2 `GET /scans`

List scan runs, most recent per repository ordering, with optional filters.

| Param | Type | Location | Required | Notes |
|---|---|---|---|---|
| `strategy_id` | string | query | no | e.g. `launchpad`, `lynch` |
| `universe_id` | string | query | no | e.g. `sp500` |
| `since` | date (`YYYY-MM-DD`) | query | no | inclusive lower bound on `scan_date` |
| `until` | date (`YYYY-MM-DD`) | query | no | inclusive upper bound on `scan_date` |
| `limit` | int | query | no | default `50`, min `1`, max `500` |

```bash
curl -s "$BASE_URL/scans?strategy_id=launchpad&universe_id=sp500&since=2026-08-01&limit=10" | jq .
```

200 OK (array of `ScanRunSummary`):
```json
[
  {
    "id": 4821,
    "scan_date": "2026-09-10",
    "scan_time": "2026-09-10T21:05:11",
    "strategy_id": "launchpad",
    "universe_id": "sp500",
    "universe_size": 503,
    "tier1_count": 12,
    "tier2_count": 34,
    "tier3_count": 0,
    "filtered_count": 41,
    "actionable_count": 46,
    "regime_label": "risk-on",
    "regime_multiplier": 1.1
  }
]
```

Edge cases:
- No matching runs → **200** with `[]` (not a 404 — this is a list endpoint).
- `limit=0` or `limit=501` → **422** (`Query(ge=1, le=500)` constraint).
- `since=13-45-2026` (bad date format) → **422**.

---

### 2.3 `GET /scans/latest`

Most recent run for a strategy/universe (optionally pinned to a specific
`scan_date`).

| Param | Type | Location | Required | Notes |
|---|---|---|---|---|
| `strategy_id` | string | query | no | default `"launchpad"` |
| `universe_id` | string | query | no | — |
| `scan_date` | date | query | no | — |

```bash
curl -s "$BASE_URL/scans/latest?strategy_id=launchpad&universe_id=sp500" | jq .
```

200 OK: same shape as one `ScanRunSummary` object (see §2.2).

Edge cases:
- No matching run → **404** `{"detail": "No matching scan run"}`
  (explicit `HTTPException` in `routers/scans.py`).
- Unknown `strategy_id` (typo, e.g. `launhcpad`) → **404**, same message —
  the route does not validate against a known-strategy list, it just finds
  no row.

---

### 2.4 `GET /scans/{run_id}/report`

Full per-ticker report for one scan run.

| Param | Type | Location | Required | Notes |
|---|---|---|---|---|
| `run_id` | int | path | yes | scan_runs.id |

```bash
curl -s "$BASE_URL/scans/4821/report" | jq .
```

200 OK (`ScanReport`):
```json
{
  "strategy_id": "launchpad",
  "universe_id": "sp500",
  "scan_date": "2026-09-10",
  "scan_time": "2026-09-10T21:05:11",
  "scan_summary": { "universe_size": 503, "actionable_count": 46 },
  "market_regime": { "label": "risk-on", "multiplier": 1.1 },
  "tickers": [
    { "ticker": "AAPL", "eligible": true, "tier": "tier1", "final_score": 87.3 }
  ]
}
```
`tickers[]` entries are `extra="allow"` — strategy-specific fields beyond
`ticker`/`eligible`/`tier`/`final_score` will also be present; treat the
schema above as a minimum, not exhaustive, contract.

Edge cases:
- `run_id` not found → **404** `{"detail": "No scan run with id <id>"}`.
- `run_id=abc` (non-integer path param) → **422**.

---

### 2.5 `GET /tickers/{ticker}/history`

Paginated scan-appearance history for one ticker.

| Param | Type | Location | Required | Notes |
|---|---|---|---|---|
| `ticker` | string | path | yes | not case-normalized on input, but response echoes `.upper()` |
| `actionable_only` | bool | query | no | default `true` |
| `strategy_id` | string | query | no | — |
| `universe_id` | string | query | no | — |
| `since` | date | query | no | — |
| `until` | date | query | no | — |
| `limit` | int | query | no | default `50`, min `1`, max `500` |
| `offset` | int | query | no | default `0`, min `0` |

```bash
curl -s "$BASE_URL/tickers/AAPL/history?actionable_only=true&strategy_id=launchpad&limit=20&offset=0" | jq .
```

200 OK (`TickerHistoryPage`):
```json
{
  "ticker": "AAPL",
  "total": 37,
  "limit": 20,
  "offset": 0,
  "rows": [
    { "run_id": 4821, "scan_date": "2026-09-10", "strategy_id": "launchpad", "universe_id": "sp500", "ticker": "AAPL" }
  ]
}
```

Edge cases:
- Unknown ticker (no history) → **200** with `"total": 0, "rows": []`
  (no 404 path — this endpoint always returns a page shape).
- `offset` beyond `total` → **200** with `"rows": []`.
- `limit=501` → **422**.

---

### 2.6 `GET /command-center`

Launchpad/Lynch coverage, deltas, overlap, and a cross-universe actionable
ticker list for one scan date — same payload the dashboard's Command Center
page and the digest job use (`quant_hub/digest/command_center.py`).

`actionable_tickers` is a flat, pre-sorted (`final_score` desc) list merging
every universe/strategy's actionable rows for the date — the lightweight
`ticker/tier/eligible/sector_etf/final_score` projection (no per-factor score
breakdown; that requires `GET /scans/{run_id}/report` for the specific run),
annotated with `universe_id`/`run_id`/`regime_label`/`scan_time` so a
cross-universe "what to look at today" view doesn't need to fan out to
every universe's full report just to find the handful of actionable rows.

| Param | Type | Location | Required | Notes |
|---|---|---|---|---|
| `scan_date` | date | query | no | defaults to **today** (server-side `date.today()`) if omitted |

```bash
curl -s "$BASE_URL/command-center?scan_date=2026-09-10" | jq .
```

200 OK (no declared `response_model` — plain dict; shape from
`build_command_center_payload`):
```json
{
  "scan_date": "2026-09-10",
  "generated_at": "2026-09-10T21:10:00+00:00",
  "regime_label": "risk-on",
  "regime_multiplier": 1.0,
  "run_count": 2,
  "per_strategy": {
    "launchpad": { "actionable": 46, "tier1": 12, "universes": 1 },
    "lynch": { "actionable": 8, "tier1": 2, "universes": 1 }
  },
  "coverage": [
    {
      "strategy_id": "launchpad",
      "strategy_label": "Launchpad",
      "universe_id": "sp500",
      "run_id": 4821,
      "actionable_count": 46,
      "tier1_count": 12,
      "tier2_count": 34,
      "regime_label": "risk-on",
      "scan_time": "2026-09-10T21:05:11"
    }
  ],
  "actionable_tickers": [
    {
      "ticker": "AAPL",
      "tier": "tier1",
      "eligible": true,
      "sector_etf": "XLK",
      "final_score": 87.3,
      "strategy_id": "launchpad",
      "universe_id": "sp500",
      "run_id": 4821,
      "regime_label": "risk-on",
      "scan_time": "2026-09-10T21:05:11"
    }
  ],
  "launchpad_lynch_overlap": [
    { "ticker": "AAPL", "launchpad": { "tier": "tier1", "final_score": 87.3, "universe_id": "sp500" }, "lynch": { "tier": "tier2", "final_score": 61.0, "universe_id": "sp500" } }
  ],
  "overlap_count": 1
}
```

Edge cases:
- No scans exist for `scan_date` (including today, if the scan hasn't run
  yet) → **200** with an empty-coverage payload (`run_count: 0`,
  `coverage: []`, `launchpad_lynch_overlap: []`) — **not** a 404, matching
  dashboard behavior by design (see the route's own docstring).
- Bad `scan_date` format → **422**.

---

### 2.7 `GET /outcomes`

Forward-return outcomes for tickers, in one of two mutually exclusive
query modes.

| Param | Type | Location | Required | Notes |
|---|---|---|---|---|
| `run_id` | int | query | one of `run_id`/`ticker` | outcomes for every ticker in one scan run |
| `ticker` | string | query | one of `run_id`/`ticker` | cross-run outcomes for one ticker (any case — uppercased server-side); joins `scan_runs` so each row also carries `strategy_id`/`universe_id`/`scan_date` |
| `strategy_id` | string | query | no | only meaningful with `ticker` mode |
| `horizon_days` | int | query | no | filters to one horizon if given, either mode |
| `limit` | int | query | no | `ticker` mode only; default `100`, max `500` |

```bash
curl -s "$BASE_URL/outcomes?run_id=4821&horizon_days=20" | jq .
curl -s "$BASE_URL/outcomes?ticker=AAPL&strategy_id=launchpad" | jq .
```

200 OK (array of `OutcomeRow`):
```json
[
  {
    "run_id": 4821,
    "ticker": "AAPL",
    "horizon_days": 20,
    "anchor_date": "2026-09-10",
    "forward_return_pct": 4.2,
    "forward_max_gain_pct": 6.1,
    "forward_max_drawdown_pct": -1.8,
    "spy_forward_return_pct": 1.5,
    "excess_return_pct": 2.7,
    "label_binary": true,
    "label_status": "ok",
    "computed_at": "2026-10-08T00:00:00",
    "strategy_id": "launchpad",
    "universe_id": "sp500",
    "scan_date": "2026-09-10"
  }
]
```

`strategy_id`/`universe_id`/`scan_date` are only populated in `ticker`
mode (they come from a join to `scan_runs`; `signal_outcomes` itself has
no such columns) — `null` in `run_id` mode. `label_status` is one of
`ok` (the previous doc example, `"resolved"`, was never a real value —
see `ml/constants.py`), `no_price`, `insufficient_future_bars`, or
`invalid_anchor`; only `ok` rows have real numbers in the return/drawdown
fields. There is no literal "pending" status in practice — a signal whose
horizon hasn't elapsed yet simply has no row at all, in either mode.

Edge cases:
- **Neither `run_id` nor `ticker` given** → **422**
  `{"detail": "Provide either run_id or ticker"}`.
- `run_id` or `ticker` with no matching outcomes yet → **200** with `[]`.
- Invalid `run_id` type (e.g. `run_id=abc`) → **422**.

---

### 2.8 `GET /outcomes/status`

Count of outcome rows grouped by `label_status`.

| Param | Type | Location | Required | Notes |
|---|---|---|---|---|
| — | — | — | — | no parameters |

```bash
curl -s "$BASE_URL/outcomes/status" | jq .
```

200 OK (plain `dict[str, int]`, no declared schema):
```json
{ "resolved": 812, "pending": 46 }
```

Edge cases: none — no inputs, no error paths. An empty table returns `{}`.

---

### 2.9 `GET /models`

Research model registry (metadata only — **no live inference**, per the
route's own docstring / `docs/ARCHITECTURE_GAPS.md` P2).

| Param | Type | Location | Required | Notes |
|---|---|---|---|---|
| `strategy_id` | string | query | no | — |
| `universe_id` | string | query | no | — |
| `status` | string | query | no | e.g. `active`, `retired` (whatever values exist in the table — not enum-validated) |
| `limit` | int | query | no | default `50`, min `1`, max `200` |

```bash
curl -s "$BASE_URL/models?strategy_id=launchpad&status=active&limit=10" | jq .
```

200 OK (array of `ModelSummary`):
```json
[
  {
    "id": 12,
    "name": "launchpad-xgb-v3",
    "strategy_id": "launchpad",
    "universe_id": "sp500",
    "horizon_days": 20,
    "status": "active"
  }
]
```

Edge cases:
- No matching models → **200** with `[]`.
- `limit=201` → **422** (max is 200 here, not 500 — narrower than
  `/scans` and `/tickers/*/history`).
- Unrecognized `status` value (e.g. a typo) → **200** with `[]`, since it's
  a plain equality filter, not a validated enum.

---

## 3. Sequential Test Workflow

A suggested order to validate the whole read path end-to-end, from
infrastructure up to data:

```bash
BASE_URL="http://localhost:5010"

# 1. Confirm the container stack is healthy
docker ps --filter "name=quant-hub" --format "table {{.Names}}\t{{.Status}}"

# 2. Confirm the API process is up and can reach Postgres
curl -s "$BASE_URL/healthz" | jq .

# 3. Confirm at least one scan run exists (pick a strategy/universe you expect data for)
curl -s "$BASE_URL/scans?strategy_id=launchpad&limit=5" | jq .

# 4. Grab the latest run for that strategy — note its "id"
RUN_ID=$(curl -s "$BASE_URL/scans/latest?strategy_id=launchpad" | jq -r .id)
echo "Latest run: $RUN_ID"

# 5. Pull the full per-ticker report for that run
curl -s "$BASE_URL/scans/$RUN_ID/report" | jq '.tickers | length'

# 6. Spot-check one ticker's history across runs
curl -s "$BASE_URL/tickers/AAPL/history?limit=5" | jq .

# 7. Pull the Command Center rollup for that run's scan_date
SCAN_DATE=$(curl -s "$BASE_URL/scans/$RUN_ID/report" | jq -r .scan_date)
curl -s "$BASE_URL/command-center?scan_date=$SCAN_DATE" | jq '.run_count, .overlap_count'

# 8. Check outcome resolution status, then pull outcomes for the run
curl -s "$BASE_URL/outcomes/status" | jq .
curl -s "$BASE_URL/outcomes?run_id=$RUN_ID" | jq .

# 9. List any registered models for the strategy
curl -s "$BASE_URL/models?strategy_id=launchpad" | jq .
```

If step 3 returns `[]`, everything downstream (steps 4-9) will legitimately
return empty/404 — that's a data-availability issue, not an API bug. Check
whether the scan job has run for that environment before assuming the API
is broken.

---

## 4. Troubleshooting

### Container status & logs

```bash
# Is the API container running at all?
docker ps -a --filter "name=quant-hub-api"

# Tail API logs (uvicorn access/error log + app logging via logging_setup)
docker logs -f quant-hub-api-dev          # dev
docker logs -f quant-hub-api              # prod
docker logs -f quant-hub-api-stage        # stage

# Last 100 lines only, with timestamps
docker logs --tail 100 -t quant-hub-api-dev
```

### Postgres connectivity

```bash
# Is Postgres healthy? (compose healthcheck runs pg_isready)
docker inspect --format='{{.State.Health.Status}}' quant-hub-db-dev

# Tail Postgres logs for connection errors
docker logs -f quant-hub-db-dev

# From the host, using the mapped dev port
psql "postgresql://quant:dev-only-change-me@localhost:5433/quant_hub_dev" -c '\dt'
```

### Common failure signatures

| Symptom | Likely cause | Where to look |
|---|---|---|
| `/healthz` returns `{"status":"degraded","database":false}` | Postgres unreachable/not ready, or `DATABASE_URL` misconfigured | `docker logs quant-hub-api-dev`, `docker inspect` health on the `postgres` container, `.env.dev` `DATABASE_URL` |
| `curl: (7) Failed to connect` | API container not running, or wrong `API_PORT` | `docker ps`, confirm `${API_PORT}` in the env file matches your `BASE_URL` |
| Every list endpoint returns `[]` | No scan runs in this environment/DB yet (not a bug) | `/scans` with no filters, then check the scan job's own logs/scheduler, not the API |
| 422 on a request that "looks right" | Query param type mismatch (e.g. date not `YYYY-MM-DD`, string where int expected) | Compare against the parameter tables in §2; `$BASE_URL/openapi.json` has the exact expected types |
| API container restarting in a loop | Startup failure — bad `DATABASE_URL`, missing env var, import error | `docker logs quant-hub-api-dev` (uvicorn prints the traceback before exit) |

### Rebuild after a code change

```bash
# API and dashboard share one image — rebuild picks up either
./scripts/run_env.sh dev up -d --build
```

---

## Scope note

This document was generated by a **read-only** review of
`src/quant_hub/api/` (routers, schemas, deps, app factory) plus the
compose/env files that wire the service up. No application code was
modified to produce it. If routes change, regenerate rather than
hand-patch, so this stays a faithful mirror of the code.
