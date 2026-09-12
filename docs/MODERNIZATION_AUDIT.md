# Quant Hub Modernization Audit

**Scope:** Read-only architecture, UI, and API-decoupling audit of the Launchpad/Lynch research stack
**Method:** Static code review only — no `EXPLAIN ANALYZE`, load testing, or production telemetry
**Branch reviewed:** `dev`
**Date:** 2026-09-11

See also: [Architecture Gaps](ARCHITECTURE_GAPS.md) (operational/security risk register) and [Data Model](DATA_MODEL.md) (schema reference) — this audit treats their findings as given and does not re-derive them.

## Contents

- [00 · Executive summary](#00--executive-summary)
- [01 · Architecture & data flow audit](#01--system-architecture--data-flow-audit)
- [02 · Frontend & UI assessment](#02--existing-frontend--ui-assessment)
- [03 · Modernization blueprint & API decoupling plan](#03--ui-modernization-blueprint--api-decoupling-plan)
- [04 · Modernization roadmap](#04--modernization-roadmap)
- [05 · Training data guardrails (ML/LLM)](#05--training-data-guardrails-mlllm)

---

## 00 · Executive summary

Quant Hub is a well-structured single-tenant research tool: cron → scoring engine → Postgres repository pattern → Streamlit. The persistence layer is sound. The strain is concentrated in two places — how the dashboard *reads* that data, and the total absence of a boundary between the scoring engine's internal report shape and the UI.

- **The repository layer is the right seam for an API.** `ScanRepository`, `OutcomesRepository`, and `MlModelsRepository` already isolate every SQL statement behind typed Python methods — a FastAPI layer can wrap these directly rather than rebuilding persistence.
- **The Command Center page is the sharpest performance finding.** Rendering one date's cross-scanner rollup issues on the order of 60–70 discrete queries (a per-run N+1 fan-out), each opening its own unpooled Postgres connection.
- **The dashboard and the scoring engine share one object.** `dashboard/viz/data.py` reaches directly into the same JSONB shape the engine writes — there is no DTO boundary today, which is exactly what an API decoupling phase must introduce.
- **Streamlit's execution model, not any one file, is the usability ceiling.** Every filter or selection re-runs the entire script; only 2 of roughly 15 data-loading paths are cached, and none of the Postgres reads are.
- **Scale is modest and that matters for sequencing.** This is a single/small-team homelab tool (~8–10 scan runs/day). The findings below are real, but the roadmap in §04 deliberately front-loads cheap fixes (pooling, one index, caching) before any rewrite — not a scale-driven rearchitecture.

Query-count and connection-count figures below are derived by tracing call paths in code, not measured at runtime.

---

## 01 · System architecture & data flow audit

How a scan goes from `docker/crontab` to a rendered dashboard row, and where the pipeline is tightly coupled or under-indexed.

### 1.1 · End-to-end pipeline (ingestion → storage → consumption)

Two independent scanners — **Launchpad** (technical/quality) and **Lynch** (fundamentals) — run on a fixed ET schedule and write into the same Postgres schema through one shared repository. Nothing reads the database except the Streamlit app, the email digest job, and the ML labeling job; there is currently no other consumer, which is exactly why a new API can be introduced additively.

```text
Cron (docker/crontab, ET)
        │
        ▼
CLI entrypoints (quant-launchpad*, quant-lynch*)
        │
        ▼
Scoring engine (ScanService → report dict)
        │
        ▼
ScanRepository.upsert_scan()
        │
        ▼
Postgres: scan_runs + ticker_results.detail (JSONB)
        │
   ┌────┼──────────────────────┬───────────────────────┐
   ▼                           ▼                        ▼
Streamlit dashboard      Email digests            ML labeling
ScanRepository           quant-digest              signal_outcomes
.load_report() /         (daily / weekly)          → ml_models
.ticker_history()                                  (no live inference —
⚠ Command Center:                                   research only)
N+1 fan-out (§1.3)
```

`scan_date · strategy_id · universe_id` is the natural key everywhere below the write step — a rerun of the same day/product/universe replaces the prior snapshot. All three consumers read the same two tables through the same repository class — there is no separate read path today, which is both the risk (§1.3) and the opportunity (§03).

### 1.2 · The repository layer & JSONB transformation

`src/quant_hub/infrastructure/postgres/repository.py` (953 lines) is the entire data-access surface for scans. Writes are straightforward: `upsert_scan()` (`repository.py:110`) inserts one aggregate row into `scan_runs` keyed on `(scan_date, strategy_id, universe_id)`, then deletes and bulk-re-inserts every ticker for that run into `ticker_results`, storing the **entire per-ticker report object** — scores, eligibility, tier, sector — as a single `detail JSONB` column (`repository.py:186`).

Reads reverse this: `load_report()` (`repository.py:253`) fetches the aggregate row, restores `market_regime` and tier counts from `scan_runs.metadata`, then selects `detail` for every ticker in the run and hands back the reconstructed report — the same shape the engine originally produced. `ticker_history()` (`repository.py:405`) does the equivalent join across runs, and — notably — the "is this row actionable" filter is applied **in Python** after the JSONB is already fetched (`is_actionable()`, `history/actionable.py`), not pushed into SQL.

**Coupling finding:** Because `detail` is the engine's raw report object, the dashboard (`dashboard/viz/data.py`) unpacks it directly — `t["summary"]["final_adjusted_score"]`, `t["scores"][key]["score"]`, `t["eligibility"]["fail_reason"]`. There is no DTO between "what the engine computed" and "what the UI renders." A scoring-engine change is, today, a dashboard-breaking change with no version marker on the row itself to detect it.

### 1.3 · Bottlenecks, coupling, and indexing

| Finding | Evidence | Impact | Severity |
|---|---|---|---|
| No connection pooling — every repository call opens a fresh `psycopg.connect()` | `connection.py:16–22`, 33 call sites | Fine for one Streamlit process today; would not survive concurrent API traffic unchanged | **High** |
| Command Center N+1 fan-out: `_persistent_symbols()` issues up to 5 sequential per-run queries, plus one `_prior_run` query, per scanned run | `digest/command_center.py:16–73` | ≈60–70 short-lived queries/connections to render one Command Center page for a day's ~8 runs | **High** |
| Engine report ↔ UI have no DTO boundary; `detail` JSONB is unpacked ad hoc by the dashboard | `dashboard/viz/data.py`, `repository.py:29–56` | No seam to insert an API today without duplicating unpacking logic; blocks §03 until addressed | **High** |
| Filtering (tier, min score, ticker search) happens client-side in Python after the *full* universe's JSONB is loaded | `dashboard/app.py:123–128`, `pages/launchpad.py` | A single-ticker search still pulls and deserializes the whole universe's detail column | Medium |
| `ticker_results.detail` carries no schema-version marker (only `scan_runs.metadata.schema_version` exists) | `repository.py:18` | An engine change can silently alter the shape of historical rows the dashboard must still render | Medium |
| No composite index on `scan_runs(strategy_id, universe_id, scan_date)`, the exact triple `list_runs_filtered` / `_prior_run` filter on | `schema.sql:45–47` | Negligible today (~8–10 rows/day); compounds as scan history accumulates with no retention policy (see `docs/ARCHITECTURE_GAPS.md` P4) | Low |

---

## 02 · Existing frontend & UI assessment

~4,400 lines across 20 files under `dashboard/viz/`, orchestrated by a 214-line `app.py`. The code is organized well by responsibility; the ceiling is Streamlit's own execution model, not the code.

### 2.1 · Component map

| Module(s) | Responsibility | Size |
|---|---|---|
| `sidebar.py` | Strategy / universe / scan-date selectors, filter controls, the global ticker-lookup omnibar. Every widget writes to `st.session_state` and triggers a full rerun. | 234 lines |
| `pages/launchpad.py` + `launchpad_overview.py` + `launchpad_insights.py` | Launchpad's five tabs: Overview, Full Universe, Ticker Detail, Watchlist, Compare | 1,450 lines |
| `lynch_components.py` + `lynch_data.py` | Fundamental-screen views: category counts, PEG/score tables, qualitative overlay | 448 lines |
| `pages/command_center.py` + `digest/command_center.py` | Cross-scanner daily rollup: coverage heatmap, Launchpad∩Lynch overlap, day-over-day deltas — the query hotspot from §1.3 | ~600 lines |
| `ticker_history_components.py` + `navigation.py` | Per-ticker drill-down panel and the session-state routing that lets any table row open it | 315 lines |
| `components.py` | Shared score cards, news panel, price snapshot — the *only* module using `st.cache_data`, and only for external Yahoo fetches, not Postgres reads | 565 lines |
| `styles.py` + `design_tokens.py` | Hand-written CSS injected via `st.markdown(..., unsafe_allow_html=True)` to make native widgets read as a dashboard | 276 lines |

### 2.2 · How input reaches the repository

The path from a sidebar click to a SQL query is short and traceable, but it re-runs the whole page every time: `render_sidebar_controls()` (`sidebar.py:80`) returns `(strategy_id, universe_id, scan_date, filters)` on every script execution; `app.py:123` immediately calls `repo.load_report(...)` with those values — a full JSONB fetch for the entire selected universe, every time *any* sidebar widget changes, including widgets (like the tier filter) that only need to affect client-side rendering.

### 2.3 · Usability limitations

- **Full-script reruns.** Streamlit's model re-executes `app.py` top-to-bottom on any widget change — there is no partial update, so choosing a universe then a date then a filter is three independent full reruns and three independent repository round-trips.
- **Almost nothing is cached.** Only `_load_ticker_news` and `_load_ticker_snapshot` use `st.cache_data` (`components.py:348–355`), and both cache external Yahoo calls — none of the ~15 Postgres read paths are cached at any TTL.
- **No pagination or virtualization on tables.** `st.dataframe(..., on_select="rerun")` appears at 9 call sites; each row selection is itself a full script rerun, and a 500+-row universe (`full_universe_dataframe`) is rendered in one shot with no windowing.
- **Layout ceiling.** `st.columns(n)` is the finest layout primitive available; there are no real responsive breakpoints, so the "wide" layout is desktop-first and simply compresses on narrow viewports rather than re-flowing.
- **The framework's styling has already been outgrown.** 276 lines of custom CSS, injected as raw HTML, are required to get a dashboard look out of native Streamlit widgets — including ticker-derived strings interpolated into HTML in `command_center.py`'s header, a pattern `docs/ARCHITECTURE_GAPS.md` already flags for escaping.
- **No live updates.** A cron job landing a new scan does not reach an open browser tab — the model has no push channel from Postgres to the client; seeing new data means a manual reload.

---

## 03 · UI modernization blueprint & API decoupling plan

The repository classes already isolate every query. Decoupling is mostly a matter of putting a typed HTTP contract in front of methods that exist, then building a frontend against that contract instead of against Postgres shapes.

### 3.1 · Backend decoupling — proposed API contract

A thin FastAPI service (`quant_hub.api`) sitting beside — not inside — the existing CLI. The CLI keeps writing exactly as it does today; the API only reads. v1 is a pass-through over methods that already exist on `ScanRepository` / `OutcomesRepository` / `MlModelsRepository`:

| Endpoint | Backed by | Change from today |
|---|---|---|
| `GET /scans` | `list_runs_filtered()` | Expose strategy / universe / date-range / limit as query params — already supported internally |
| `GET /scans/latest` | `get_latest_run()` | Direct pass-through |
| `GET /scans/{run_id}/report` | `load_report()` | Response becomes a versioned Pydantic model instead of raw JSONB reflection |
| `GET /tickers/{ticker}/history` | `ticker_history()` / `ticker_history_count()` | Server-side pagination already exists (`limit`/`offset`) — just needs exposing over HTTP |
| `GET /command-center` | `build_command_center_payload()` | **Fix the N+1 fan-out (§1.3) before exposing this one** — otherwise the API inherits the dashboard's slowest path |
| `GET /outcomes` | `OutcomesRepository.list_outcomes_for_run()` / `count_by_status()` | Direct pass-through |
| `GET /models` | `MlModelsRepository` (registry list) | Direct pass-through; still research-only, no inference endpoint (matches current scope) |

The response model is where the real work is — turning the ad hoc `detail` JSONB into a typed, versioned contract:

```python
class TickerDetail(BaseModel):
    schema_version: int
    ticker: str
    eligible: bool
    tier: str
    final_score: float | None
    scores: dict[str, ScoreComponent]
    eligibility: EligibilityDetail | None
    # unknown/legacy keys tolerated, not silently dropped or 500'd
    class Config:
        extra = "allow"
```

Three infrastructure changes belong in the API layer, not in a rewrite of persistence: a shared `psycopg_pool.ConnectionPool` at app startup (replacing per-call `connect()`), SQL-level filtering for tier/score/search instead of loading-then-filtering in Python, and the composite index from §1.3 landing before the API takes real traffic.

### 3.2 · Frontend architecture recommendation

| Layer | Recommendation | Why / tradeoff |
|---|---|---|
| App shell | **Vite + React + TypeScript** | Single-tenant, behind-VPN research tool — no SSR or multi-tenant routing need justifies Next.js's weight. Reconsider Next.js only if auth middleware ends up living in the frontend tier. |
| Styling | Tailwind CSS | Replaces the 276 lines of hand-written CSS in `styles.py` with a maintainable utility system |
| Components | shadcn/ui | Accessible primitives for exactly what's already hand-built today — the ticker-lookup omnibar, selects, dialogs |
| Data tables | **TanStack Table** (headless) | Virtualization, server-side sort/filter/pagination for 500+-row universes. AG Grid only if inline cell editing or Excel-style export becomes an actual requirement — it's the heavier option for a read-only tool. |
| Charts — categorical/heatmap | Plotly.js (React wrapper) | Keeps the coverage heatmap and regime charts conceptually reusable from today's figure logic |
| Charts — price/OHLCV | Lightweight Charts (TradingView) | Purpose-built for scrolling candle/volume data if a price panel is added — Plotly is the wrong tool for that specific job |

### 3.3 · Data table & charting specs

- **Full-universe table** — columns: ticker, tier (badge), final score, five Launchpad score components as inline mini-bars, filter reason. Row virtualization above ~150 rows; server-driven filter/sort replacing the current client-side Python pass over the full JSONB.
- **Ticker history table** — already paginated server-side in the repository (`limit`/`offset` in `ticker_history()`); the frontend work is wiring TanStack Table's pagination controls to those existing params, not inventing new ones.
- **Command Center heatmap** — same strategy × universe matrix as today's Plotly heatmap, served pre-aggregated by the fixed `/command-center` endpoint rather than assembled client-side.
- **Score sparklines** — small multiples per ticker row for the five Launchpad components (macd zero-line, squeeze intensity, tightness percentile, volume vacuum, trend/proximity) — currently only visible one-ticker-at-a-time in the Ticker Detail tab.

---

## 04 · Modernization roadmap

Five phases, each shippable on its own, each leaving the previous phase's users unaffected. Nothing in Phase 0–2 requires retiring Streamlit.

| Phase | Focus | Detail | Status change |
|---|---|---|---|
| **Phase 0** | Harden what exists | Add `psycopg_pool` pooling, the `scan_runs(strategy_id, universe_id, scan_date)` index, fix the Command Center N+1 in the repository layer, and wrap the existing Postgres reads in `st.cache_data`. | No API surface change |
| **Phase 1** | API layer, additive | Ship the FastAPI read-service from §3.1 beside the current Streamlit app. Both hit the same Postgres. Exit criteria: basic contract tests, since the repo has none today. | Streamlit unaffected |
| **Phase 2** | Design system | Scaffold Vite + React + Tailwind + shadcn/ui against the Phase 1 API. Build in parallel; nothing is cut over. This is where the table/chart specs in §3.3 get built and validated. | No user-facing change yet |
| **Phase 3** | Screen-by-screen migration | Command Center first — most self-contained page, and the biggest current pain point once Phase 0 fixes it. Old and new UIs run side-by-side behind the same reverse proxy. | Incremental cutover |
| **Phase 4** | Cutover | Retire the Streamlit dashboard once all tabs are ported. Keep `quant-view` as a one-release fallback before deletion, not a permanent second UI. | Streamlit retired |

### Migration risks

| Risk | Detail | Mitigation |
|---|---|---|
| JSONB → typed schema drift | Historical `ticker_results.detail` rows predate any contract and won't all match a strict schema | Tolerant/optional Pydantic fields (`extra = "allow"`) rather than retrofitting strict validation onto old rows |
| No CI today | `docs/ARCHITECTURE_GAPS.md` H6 — no lint/test/schema CI exists | Add API contract tests as a Phase 1 exit criterion, before any frontend work depends on the API being stable |
| Second reachable surface | A REST API is a new network surface next to the already-unauthenticated dashboard (`docs/ARCHITECTURE_GAPS.md` C1/C2) | Put the API behind the same authenticated reverse proxy/VPN boundary *before* Phase 1 ships, not after |
| Command Center inheriting slowness | If exposed before Phase 0 lands, `/command-center` would carry the N+1 fan-out into the API | Sequencing dependency: Phase 0's repository fix is a hard prerequisite for that one endpoint, not a nice-to-have |
| Over-building for scale that doesn't exist | This is a single/small-team tool at ~8–10 scans/day, not a multi-tenant product | Pooling + one index + caching is the right size of fix; no need for read replicas, message queues, or a services split |

---

## 05 · Training data guardrails (ML/LLM)

**Trigger:** this data (Launchpad/Lynch scan history, forward-return labels) is a planned source for both the existing scikit-learn-style Launchpad model and a future LLM fine-tune/RAG corpus. Confirmed before starting modernization: quality gating existed, but only on one of the two paths that read it.

### 5.1 · What already exists

The repository already computes real quality signals at ingestion — this audit's job was to check they're *enforced*, not just recorded.

| Control | Where | What it catches |
|---|---|---|
| OHLCV validation (staleness, spike, incomplete last bar) | `data/quality.py` (`validate_ohlcv`, `ohlcv_is_stale`, `has_price_spike`) | Bad/partial Yahoo price bars before they reach scoring |
| Fundamentals/Lynch fetch-quality summary | `data/quality.py:lynch_metrics_quality_summary`, `lynch/metrics.py:248` | Missing PE/PEG/ROE/institutional fields, fetch errors, surfaced per-run in `scan_runs.metadata.metrics_quality` |
| Forward-label status | `ml/labels.py:compute_forward_outcome` → `signal_outcomes.label_status` (`ok`/`no_price`/`invalid_anchor`/`insufficient_future_bars`) | Labels computed off missing or too-short price history |
| Training-set filtering | `ml/training_set.py:build_training_frame` | Drops non-setup tiers, non-`ok` labels, missing targets, missing features (`TrainingSetStats` records every drop reason) |
| Point-in-time embargo | `ml/walk_forward.py:apply_ticker_signal_embargo` | Same-ticker signal leakage within the forward-label horizon |
| Schema/lineage versioning | `ml/constants.py:FEATURE_SCHEMA_VERSION`, stamped on every feature row | Lets a consumer detect a stale feature definition |

### 5.2 · Gap found and closed in this pass

`ml/training_set.py` (used by `quant-ml train`) enforced all of the above. `application/ml_export_service.py` (used by `quant-ml export-features`, the Parquet path most likely to leave this repo for external ML/LLM tooling) did not — it merged every ticker row regardless of tier, `label_status`, or Lynch fetch errors, with only passive flag columns for a consumer to filter themselves.

Fixed: `MLExportService.run()` now takes `quality_gate: bool = True` and applies the same filters as `training_set.py` (setup tier, `label_status == ok`, Lynch `fetch_error`, signal embargo), tracks drop counts per reason, and writes a `*.manifest.json` next to every Parquet export recording `feature_schema_version`, row counts, drop reasons, and a hard warning when the gate is explicitly disabled (`quant-ml export-features --no-quality-gate`, an audit-only escape hatch — not for training/LLM use). See `tests/unit/test_ml_export_service.py`.

### 5.3 · LLM/RAG-specific requirement

Any future text/narrative corpus built from this data (fine-tune examples, RAG documents, eval sets) must be built from a `quality_gate=True` export and must carry its manifest as provenance. The specific failure mode to guard against: **hindsight leaking into generated text.** A narrative summarizing a ticker's `detail` payload must anchor every claim to `metadata.data_provenance.as_of_price`/`scan_date` — never "as of today" — or a model trained on it learns to describe historical setups with outcome knowledge it wouldn't have had at scan time. This is the same point-in-time discipline `apply_ticker_signal_embargo` already enforces numerically; it has no analogue yet for free text, because none is generated today.

### 5.4 · Preconditions this pass does not close

Row-level gating doesn't fix dataset-level validity. Before treating an export as a trustworthy ML/LLM training source at scale, these existing gaps from `ARCHITECTURE_GAPS.md` still apply and should land ahead of or alongside Phase 0:

- **P3 — survivorship bias:** universes aren't point-in-time membership sets. A training/RAG corpus built across history implicitly excludes tickers that were later delisted or dropped from an index, biasing both labels and any generated narrative toward survivors.
- **P1 — single data provider:** Yahoo is the sole source with no retry/backoff, so incomplete-fetch rows (already filtered here) aren't rare — expect the drop counts in export manifests to be non-trivial until P1 is addressed.
- **P4 — no retention/archive policy:** `scan_runs` cascades to `ticker_results` and `signal_outcomes`; an unplanned cleanup silently shrinks or removes historical training data with no snapshot to recover from.

**Recommendation:** fold the export-path fix (done) into Phase 0 of §04 — it's a repository-layer change with no API surface impact. Treat P3/P1/P4 as prerequisites for any *broad* ML/LLM training claim, not for the guardrails themselves, which are now enforced per-export regardless.

---

**Audit scope:** `src/quant_hub/`, `scripts/`, `docker-compose*.yml`, `docker/`, and `docs/`. No files were modified, no commits made, no services started during the audit itself.
