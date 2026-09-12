# Quant Hub — Reimagined UI/UX Blueprint

**Status:** design proposal only. No application code was modified to produce
this document. Everything below is a recommendation to be reviewed, scoped,
and (selectively) approved before any implementation begins.

**Persona:** written as a senior financial analyst / fintech product
designer would brief an engineering team — opinionated, but every claim
about *this codebase* is verified against source, not assumed.

## Methodology note — what "Finqube-style" actually means here

The brief asked for heavy visual inspiration from `finqube.io`'s company
overview page. Read plainly: this session has no visual browser (confirmed
unavailable) and a text-only fetch of that URL returned nothing but the page
title — no layout, no color values, no component structure. Everything
below that references "Finqube-style" is therefore **inferred from the
genre** (letter-grade factor scores, dense fact grids, terminal-style
information density — conventions shared by Bloomberg Terminal, TradingView,
Koyfin, and yes, Finqube's own category), not a pixel-level copy of a page
neither of us can currently verify together. If you have real screenshots
or can share the rendered HTML, this document should be revised against
them rather than trusted as a literal spec of that page.

## Fact-check against this codebase

A few things in the original brief needed correcting before design work
could stand on them:

| Claim | Status | Detail |
|---|---|---|
| Tables: `scan_runs`, `ticker_results`, `signal_outcomes`, `ml_models` | ✅ Confirmed | `infrastructure/postgres/schema.sql:3,21,52,73`. `signal_outcomes` is real and is what the `/outcomes` API reads (`outcomes_repository.py`) — it's per-signal, not a generic "outcomes" entity. |
| Launchpad daily ~17:00 ET | ✅ Confirmed, more precise | `docker/crontab:12-24` — Mon–Fri, staggered 17:10/17:15/17:20/17:25 ET per universe, digest at 17:40. |
| Lynch weekly "Saturday morning" | 🟡 Partially — it's pre-dawn | `docker/crontab:29-49` — Launchpad weekly coverage 01:00–02:00 ET, then Lynch scans staggered **02:30–06:30 ET**, ML labeling ~07:00–07:36, digest 08:30. Not "morning" in the normal sense — worth being precise in any UI copy that mentions timing. |
| Multi-universe overlap query exists | ❌ **False** | No universe-to-universe overlap logic exists anywhere. All existing "overlap" code (`digest/command_center.py`, `digest/analytics.py`) computes Launchpad∩Lynch overlap for the *same ticker across strategies* — a different axis. §2 below treats this as new work, except for one case where it's now free (see §2.2). |
| `OutcomeRow` fields (12 fields incl. embargo-adjacent `label_status`) | ✅ Confirmed | `api/schemas.py:76-88`, exact match. |
| "Embargo" concept | ✅ Real, but not what "entry triggers/stop levels" implies | `ml/walk_forward.py` — `MIN_SIGNAL_EMBARGO_TRADING_DAYS = 5`, a **training-data integrity mechanism** (prevents overlapping forward-return windows from leaking across train/test splits), not a live trading risk control. See §3.2 for why this distinction matters. |

---

## Section 0 — This changes how Phase 3 should be scoped

Phase 3 in `docs/MODERNIZATION_AUDIT.md` was written as "port the old
Streamlit tabs screen-by-screen behind a reverse proxy." That assumes the
destination is a faithful port. It no longer is:

- **Today's Priorities** (shipped) has no old-tool equivalent — the old
  dashboard never had a cross-universe default landing view.
- **Ticker 360** (§1 below) would supersede, not port, the old "Ticker
  Detail" tab.
- **Scan Run Insights** (§2 below) would supersede the old "Full Universe"
  tab's funnel/coverage aspects.
- The old "Watchlist" tab was a misnomer (an auto-filter, not a persisted
  list) and shouldn't be ported as-is — a real one is new work, not a port.

**Recommendation:** don't resume Phase 3 as "port tab X to screen X."
Reframe it as *"retire each old Streamlit tab only once its superior
replacement has shipped and been used for real,"* which is what the audit's
own phased/shippable philosophy already argues for — this just makes it
explicit that the mapping from old tab → new screen is no longer 1:1.

---

## Section 1 — Ticker 360° Profile & Deep-Dive View

### 1.1 Composite score header with letter grades

The backend has numeric scores (`final_score` 0–100-ish, per-factor
`{score, max}`) and tier strings (`"Tier 1"`/`"Tier 2"`/`"Tier 3"`/
`"filtered"`) — **no letter-grade concept exists today.** This section
proposes a purely presentational mapping, computed in the frontend from
existing numbers. It does not touch `scoring/` — it's a display layer over
scores that already exist, same category as the `tierBadgeVariant` mapping
already shipped.

Proposed thresholds (tune once real score distributions are reviewed):

| Normalized score (% of max) | Grade |
|---|---|
| ≥ 90% | A+ |
| ≥ 80% | A |
| ≥ 70% | B+ |
| ≥ 60% | B |
| ≥ 50% | C+ |
| ≥ 40% | C |
| < 40% | D |

Header layout: one large composite grade (derived from `final_score` /
whatever the strategy's max score is) beside a row of compact sub-grade
chips, one per factor — reusing the same `{score, max}` shape the 5
Launchpad factors already have (`macd_zero_line`, `squeeze_intensity`,
`tightness_percentile`, `volume_vacuum_depth`, `trend_proximity_match`),
each independently graded on the same 0–100% scale.

**Resolved — Lynch does NOT get the letter-grade treatment above.**
Research (2026-09-12) traced Lynch's scoring end-to-end
(`lynch/runner.py`, `lynch/filters.py`, `lynch/categories.py`,
`lynch/config.py`) and found a fundamentally different paradigm: boolean
pass/fail checks aggregated into one `lynch_score` percentage — **no
per-factor `{score, max}` exists to grade**. Forcing letter grades onto
it would fabricate a rubric the data doesn't have. Correct treatment:

- **`categories`** (a *non-exclusive set* — `fast_grower`/`stalwart`/
  `asset_play`; a ticker can be more than one at once) as color-coded
  badges, not grades. The old Streamlit dashboard already has a color
  convention for these (`dashboard/viz/design_tokens.py:130-135`) worth
  mirroring for consistency: fast_grower=success green, stalwart=primary,
  asset_play=accent.
- **`tier`** is a *different axis* from `categories`, not a hierarchy of
  it — one of 5 strings (`fast_grower`/`stalwart`/`asset_play`/`passed`/
  `filtered`; `tier = categories[0]` if any category matched, else
  `passed`/`filtered`). Render as its own badge, separate from the
  category badges.
- **`lynch_score`** — a single 0-100 percentage already, render as one
  gauge/progress bar. Do not decompose it into sub-grades.
- **A pass/fail checks table**, not factor grades — `detail.checks`
  already carries `label`/`passed`/`plain_value`/`threshold`/
  `why_it_matters`/`result_text` per rule (`lynch/explain.py:170-184`),
  the natural Lynch analogue to Launchpad's per-factor breakdown.
- **Individual ratios** (PE, PEG, D/E, etc.) — direct color-coded display
  against the real thresholds in `lynch/config.py`, **not** a naive
  green-high/red-low scale. Two fields are inverted from intuition:
  `institutional_pct` and `analyst_count` are **lower-is-better** (Lynch's
  "wall street neglect" — under-covered stocks are the target). Several
  other fields (P/E, P/B, dividend yield) are only meaningfully
  thresholded *within specific category contexts* (e.g. P/B only matters
  for an asset_play evaluation) — showing a color judgment on them
  outside that context would imply a rubric that wasn't actually applied
  to that ticker.

### 1.2 Unified master view (Launchpad + Lynch + ML outcomes)

Evolve the existing `TickerHistory` component (already fetches
`/tickers/{ticker}/history`) into a full profile with three stacked cards
above the existing history table:

1. **Technical (Launchpad)** — latest tier, composite grade, factor grade
   row, sparkline of `final_score` across recent appearances (data already
   in the history rows — `final_score`/`normalized_score` per run).
   **Shipped** as `TickerTechnicalCard`.
2. **Fundamental (Lynch)** — **not** the Launchpad grade pattern (see the
   correction in §1.1): category badges + a `lynch_score` gauge + a
   pass/fail checks table, with the inverted-direction fields
   (`institutional_pct`, `analyst_count`) sidestepped by rendering
   `checks[]` directly rather than re-deriving thresholds. **Shipped** as
   `TickerFundamentalCard`.
3. **ML Outcomes** — pull `signal_outcomes` rows for this ticker
   (`forward_return_pct`, `excess_return_pct`, `label_status`). The real
   distinction (corrected from an earlier draft of this doc, which
   assumed a literal "pending" status) is: **no row exists yet** for a
   signal still inside its embargo window (the actual "still waiting"
   case) vs. **a row with `label_status: "ok"`** (a real, usable number)
   vs. **a row with any other status** (`no_price`/`insufficient_future_bars`/
   `invalid_anchor` — a genuine data problem, not a timing one). **Shipped**
   as `TickerOutcomesCard`.

This required one new API surface, now shipped: `GET /outcomes` gained a
`ticker`+`strategy_id` query mode (`list_outcomes_for_ticker`, joins
`scan_runs` for context) alongside the original `run_id` mode.

### 1.3 Historical audit trail — pass-rate heatmap

**Shipped** as `TickerAuditTrail`, as a per-universe chronological strip
rather than a shared-date calendar grid (Launchpad daily vs. Lynch weekly
cadence made a shared date axis misrepresent density — see the component's
own comment). Cell intensity = tier that appearance (Tier 1 = strongest
fill, Tier 2 = medium, Tier 3/filtered = faint). **Zero new backend
work** — `/tickers/{ticker}/history` already returns
`run_id`/`scan_date`/`universe_id`/`tier` per appearance.

### 1.4 JSONB inspection engine — generalized metric grid

Rather than a hardcoded 5-factor renderer (which is what `UniverseTable`'s
current drawer does), propose a `MetricGrid` component that iterates
`Object.entries(ticker.scores)` generically: label from a lookup table
falling back to a humanized key name for anything unrecognized, a mini bar
for `{score, max}` pairs, raw value formatting (%, ratio, currency) inferred
from the `raw` payload's key naming. This survives a new factor being added
to the backend without a frontend code change — worth doing regardless of
the rest of this blueprint.

---

## Section 2 — Scan Run Insights & Multi-Universe Intelligence

### 2.1 Per-scan breakdown view

Every report already carries a `scan_summary` (`universe_size`,
`eligible_count`, `excluded_count`, `tier_counts`, `actionable_count`,
`filter_breakdown`) — typed in `lib/api.ts` today but not yet rendered
anywhere. This is a **zero-new-backend** visualization: a funnel or
stacked horizontal bar from `universe_size` down through
`filter_breakdown`'s reasons to `eligible_count` to each tier count.
Recommend a plain div/CSS stacked bar (same technique as the existing
`FactorSparkbars`) over introducing a chart library just for this one
view — keep the dependency footprint down.

### 2.2 Multi-universe overlap matrix

The fact-check above found no backend query for this — but there's a free
win here: `/command-center`'s `actionable_tickers` field (shipped this
session) already merges every actionable ticker across all universes for
a strategy/date, each row carrying `ticker` + `universe_id`. **Grouping
that list client-side by `ticker` and filtering to entries appearing under
more than one `universe_id` produces the overlap matrix with no new
backend work at all** — a direct sequencing win from the `Today's
Priorities` work already shipped. Render as: Ticker | Universes (badge
list) | Best tier | Best score.

(A true backend-side query would still be worth adding eventually for
historical/multi-day overlap analysis beyond "today," but the live case
is free right now.)

---

## Section 3 — Actionable Setup & High-Density Data Tables

### 3.1 Full-universe interactive table upgrade

`UniverseTable` already has universe filtering, tier badges, actionable
badges, and inline factor sparkbars — most of this ask is an **incremental
upgrade**, not a rewrite:

- **Sorting:** add `rowSortingFeature` + `createSortedRowModel()` to the
  existing `tableFeatures({})` call (TanStack Table v9's own migration
  docs, already vendored in `node_modules/@tanstack/react-table/skills/`,
  cover this exactly).
- **Virtualization:** `@tanstack/react-virtual` is the natural pairing
  with the table version already in use — needed once `sp500_index`
  (~500 rows) has scan data; not urgent for the ~100-250 row universes
  currently in the dev dataset.

**Recommend staying on TanStack Table, not switching to AG Grid.** The
original audit already reasoned through this trade-off explicitly (AG
Grid only if inline editing or Excel export becomes a real requirement —
neither applies to a read-only research tool), and the v9 migration cost
is already paid. Revisit only if editing/export genuinely becomes a
requirement.

### 3.2 "Actionable Signals" dashboard

This substantially overlaps what **Today's Priorities already does**
(cross-universe, ranked, actionable-first). Recommend evolving that screen
rather than building a parallel one — add:
- ML cross-reference: join against `signal_outcomes`/`ml_models` for
  *historical* validation ("tickers that looked like this historically
  went on to do X"), not live inference — there's no live inference
  endpoint (`/models` is registry-only, matches current scope per the
  original audit).

**A firm flag, not a soft one:** the brief asks for "entry triggers, stop
levels, and embargo warnings" framed as live trade parameters. **None of
that exists in this codebase**, and "embargo" specifically means something
different here (§1.2) than a trading risk control. Entry/stop-level
generation would require genuinely new financial logic (e.g., ATR-based
stop placement) — that's a real strategy/risk-model design conversation
in its own right, not a UI/UX styling decision, and it's the kind of thing
that causes real harm if shipped half-thought-through (a user acting on a
fabricated stop level). Recommend scoping that separately and explicitly,
with your own sign-off on the actual risk methodology, rather than folding
it into this visual redesign.

---

## Section 3.5 — Carried forward from the old dashboard, not in the original brief

The Finqube brief was scoped around one reference page and didn't do a
full inventory of what the old Streamlit tool had that's still worth
keeping. Two items surfaced in review that belong in the sequence:

### Compare

The old "Compare" tab (`launchpad.py:186-238`) let a user multiselect 2-3
eligible tickers and see a radar chart + per-factor comparison table —
genuinely useful, session-only in the old tool. Rebuild as a standalone
view: ticker multiselect, radar/spider chart of the same 5 Launchpad
factors (or the generalized `MetricGrid` set from §1.4) normalized to
0-100%, plus a plain comparison table. Zero new backend work — pulls the
same per-ticker `scores` already in `/scans/{run_id}/report`.

### Watchlist (a real one this time)

The old "Watchlist" tab (`launchpad.py:150-183`) was a misnomer — an
auto-filter to Tier 1/2, not a persisted list. With a real Postgres-backed
API instead of Streamlit session state, a real one is buildable: star a
ticker, it persists across days and scans regardless of tier changes.
This needs new backend surface — a small additive table (e.g.
`watchlist_tickers(ticker, added_at, note)`) and two endpoints (add/remove,
list) — genuinely new, not a read-only pass-through like the rest of the
API layer, so scope it as its own small piece of work with the same
scrutiny as any other additive change (see `phase-scope-guard`).

---

## Section 4 — Design System & Component Specification

### 4.1 Palette

The existing system is already token-based (oklch, light + dark via
`:root`/`.dark`, semantic `success`/`warning`/`destructive` tokens added
this session). Recommend a dark-first terminal palette as new **token
values** in that same architecture, not a rebuild:

- Base surfaces: deep slate/near-black (`oklch` equivalents of the
  `#0f172a`/`#1e293b` range from the brief), promoted to `--background`/
  `--card` under `.dark`.
- Keep light mode defined (the `radix-nova` preset already ships both) —
  a terminal tool doesn't have to force dark-only, and it costs nothing
  to keep the toggle.
- Semantic green/amber/red already exist (`success`/`warning`/
  `destructive`) — extend usage, don't reinvent.

### 4.2 Component selection

| Need | Recommendation | Why |
|---|---|---|
| Data tables | **TanStack Table v9 + TanStack Virtual** (already in use) | Sunk migration cost paid; audit already reasoned against AG Grid for this tool's actual requirements |
| Heatmap / funnel charts | **Plotly.js React wrapper** | Matches the original audit's own §3.2 recommendation; keeps one charting library for the app instead of two |
| Price/candle panels (if ever added) | **Lightweight Charts (TradingView)** | Purpose-built, matches audit |
| Stat tiles / grade chips / score bars | **Existing Tailwind + shadcn primitives** (`Badge`, div-based bars) | Everything Tremor would add here can already be built with what's installed; avoids a third component paradigm alongside Radix/shadcn |
| Icons | **lucide-react** (already in use) | No change |

**Recommend against adding Tremor.** It brings its own theming/component
model that would sit awkwardly next to the Radix/shadcn system already
built — the stat-card and simple-bar use cases it targets are already
covered by what's installed.

---

## Suggested build sequence

Roughly ordered by (value ÷ new-backend-risk), not by section number:

1. **Multi-universe overlap matrix** (§2.2) — ✅ **Done.** `OverlapMatrix`, client-side only, no new backend query.
2. **Ticker 360 evolution** (§1.1, §1.2, §1.3) — ✅ **Done.** `TickerAuditTrail` (pass-rate heatmap), `TickerTechnicalCard` (Launchpad composite/factor letter grades), `TickerOutcomesCard` (ML outcomes, via the new `/outcomes?ticker=` mode), `TickerFundamentalCard` (Lynch — category badges + score gauge + checks list, per the corrected non-grade design). All four stacked above the existing paginated history table in `TickerHistory`.
3. **Compare view** (§3.5) — ✅ **Done.** `CompareTickers`, up to 4 tickers, aligned factor bars per column rather than a radar/spider chart (no charting library exists yet; Plotly is reserved for item #7 and natively supports `Scatterpolar`, so a hand-rolled SVG radar now would be thrown away later).
4. **Table sort + virtualization** (§3.1) — ✅ **Done.** `UniverseTable` migrated to TanStack Table's row model (sort by ticker/tier/score, tier ranked not alphabetical) + `@tanstack/react-virtual`. Bigger change than expected: required switching from a real `<table>` to a div-based layout (virtualization's absolute positioning doesn't work reliably inside `<tbody>`). **Not visually verified** — no browser tool this session; verified via type-safety, code review, and clean compile/HMR only. Worth a manual look (scroll behavior, expand-row height changes, header sort clicks) before trusting it fully.
5. **Scan-run funnel view** (§2.1) — zero new backend, pure new rendering.
6. **MetricGrid generalization** (§1.4) — frontend-only. The letter-grade half of this item shipped as part of Ticker 360 (item #2); MetricGrid itself (a generic, key-driven renderer for `detail.scores` so a new Launchpad factor doesn't need a frontend code change) is still open. Lynch's factor research (once a blocker) is done — see item #2.
7. **Command Center heatmap** (Plotly) — the one remaining item from the original Phase 2 spec (§3.3 of the modernization audit).
8. **Real Watchlist** (§3.5) — the one item here needing new backend surface (persistence); scope with the same rigor as any other additive change.
9. **Dark-first palette pass** — do once several of the above exist, so it themes consistently rather than piecemeal.
10. **"Actionable Signals" ML cross-reference** — needs care around historical-vs-live framing (§3.2).
11. **Entry/stop-level logic** — explicitly **not** scheduled here; needs its own risk-methodology conversation before any UI is built for it.

Phase 3 (Streamlit retirement) proceeds tab-by-tab against this sequence,
per the Section 0 reframing — not as a separate mechanical porting pass.
