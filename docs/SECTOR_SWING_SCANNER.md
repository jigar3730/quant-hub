# Sector-ETF Swing Scanner — Pipeline Reference

**Version:** 1.1 (scanner, persistence, ops + React page)
**Audience:** Analysts and operators who want to understand how the sector-ETF swing scan works, what it stores, and how to run it
**Design source:** [sector_etf_scanner_spec.md](sector_etf_scanner_spec.md)

Related docs: [User Manual](USER_MANUAL.md) · [Runbook](RUNBOOK.md) · [Data Model](DATA_MODEL.md) · [Lynch Scanner](LYNCH_SCANNER.md) · [Launchpad Scanner](LAUNCHPAD_SCANNER.md)

> **Research tool only.** Quant Hub is not a trading bot. The scanner never places orders or talks to a broker, and nothing here is a return target or a guarantee. Levels are computed from Yahoo daily bars; confirm against a live quote before acting.

---

## Table of contents

1. [What it does](#1-what-it-does)
2. [Pipeline overview](#2-pipeline-overview)
3. [Data pull and freshness](#3-data-pull-and-freshness)
4. [Rules](#4-rules)
5. [Tiers and filter reasons](#5-tiers-and-filter-reasons)
6. [Trade plan and execution assumption](#6-trade-plan-and-execution-assumption)
7. [Storage](#7-storage)
8. [Running and scheduling](#8-running-and-scheduling)
9. [React page](#9-react-page)
10. [Configuration and source code](#10-configuration-and-source-code)
11. [Why a separate pipeline (D1)](#11-why-a-separate-pipeline-d1)
12. [Deviations from the spec](#12-deviations-from-the-spec)
13. [Known limitations](#13-known-limitations)

---

## 1. What it does

Finds long, multi-day (roughly 3–10 trading days) swing setups on the ETFs in the `sector_etfs` universe (`data/universes/sector_etfs.txt`; the 16 sector/industry ETFs of `config.ALL_SECTOR_ETFS` plus whatever you add). It favors market and sector leadership (trade what is already beating SPY), a pullback that is turning up rather than a falling knife, and a stop that is defined before entry and drives position size. Output is a ranked set of **trade plans** plus a watchlist of leaders close to setting up. On many days the honest answer is "no trades" — for example when leaders fail the trend filter in a choppy market.

## 2. Pipeline overview

```text
sector_etfs universe + SPY
    → download_prices()                 [infrastructure/market/yfinance_prices.py]
    → freshness gate + partial-bar drop [sector_swing/runner.py, calendar.py]
    → scan_prices()                     [sector_swing/runner.py]
        → Rule H hygiene per ticker
        → compute_indicators() once per ticker  [sector_swing/indicators.py]
        → R2 relative-strength rank vs SPY
        → R3 trend → R4 pullback → R5 trigger → R6 stop → R7 sizing
        → portfolio gates: correlation, max new signals
    → build_report()                    [sector_swing/report.py]
    → ScanRepository.upsert_scan() + CSV/JSON/Markdown exports
```

**Entry point:** `quant-sector-swing` → `SectorSwingScanService.run()` → `SectorSwingRunner.run()`.

`scan_prices()` is pure (a price frame in, outcomes out) and takes an optional `as_of` date, so the same code can be replayed point-in-time and unit-tested without a network. Failures are isolated **per ticker** (`compute_error`); a missing benchmark or stale data aborts the run and persists nothing.

## 3. Data pull and freshness

Prices come from `download_prices()` (Yahoo, adjusted OHLC, per-ticker parquet cache). Because the scan runs premarket and the cache accepts bars up to 5 days old, the runner enforces its own gate:

1. **Expected last completed session** (`sector_swing/calendar.py`): before ~16:15 ET on a trading day it is the previous trading day, after that it is today, weekends roll back to Friday. NYSE holidays are a small hard-coded list (2025–2028); outside those years the calendar falls back to weekdays only and logs a warning.
2. Bars dated after that session are dropped (a partial "today" bar is never used).
3. If SPY's last bar is older than expected and the cache was used, re-download **bypassing the cache once**.
4. If still older: **abort** — no persist, job `failed`, non-zero exit, log line `Stale price data ...`. `--allow-stale` overrides and records `data_freshness: "stale_allowed"`.
5. A missing SPY, or too little SPY history for the 200-day SMA, is fatal. Missing or bad ETFs are not: they become `filtered` rows with a reason.

`data_freshness` is one of `fresh`, `refreshed` (a cache-bypassing refetch was needed), `stale_allowed`, `synthetic` (`--dry-run`). Cron calls the CLI with `--force-refresh`, so it normally reads `fresh`.

Historical bars are dividend-adjusted (`auto_adjust=True`) while the latest bar is the actual price. That is fine for indicators, but plan levels should be checked against a live quote.

## 4. Rules

All thresholds live in `sector_swing/config.py` (`SwingParams`). Each rule has an ID that appears in logs and in `detail.eligibility.checks[].rule`.

| ID | Rule | Default |
|----|------|---------|
| H | Hygiene | ≥ 210 bars; no NaN/spike in OHLCV; 20-day average **dollar** volume ≥ $20M; close ≥ `ETF_MIN_PRICE` |
| R1 | Regime gate | SPY close > SMA50 **and** > SMA200 (unrounded SMAs). Fails → no Tier 1 and no plan issued |
| R2 | Leadership | RS = 0.5·(ETF 63d − SPY 63d) + 0.5·(ETF 126d − SPY 126d), in percentage points. Top 4 by RS **and** RS > 0 |
| R3 | Trend | Close > SMA50, EMA20 > SMA50, ADX(14) ≥ 20 (Wilder) |
| R4 | Pullback | Within the last 6 bars, some Low ≤ EMA20 × 1.005 |
| R5 | Trigger | Close > prior bar High **and** Close > EMA10 |
| R6 | Stop | min(Low, last 6 bars) − 0.25·ATR14; rejected if risk ≤ 0 or > 2.5·ATR14 |
| R7 | Sizing | `floor(min(equity·risk% / R, equity·30% / entry))`; rejected if 0 |
| R8 | Exits (guidance) | +2R target (sell half), trail on close below EMA10, time stop after 10 days without +1R. Tracked in Phase 2 |

`ATR` is the repo's simple rolling mean (`indicators.atr`), not Wilder smoothing, so stop distances differ slightly from prototypes that use Wilder ATR. ADX lives in `sector_swing/adx.py` (`indicators.py` is untouched).

**Portfolio gates** (within one scan): at most 3 Tier 1 plans in RS-rank order; a candidate whose 60-day daily-return correlation with an already-selected plan exceeds 0.85 is skipped (`correlated`). Open-position awareness arrives in Phase 2.

## 5. Tiers and filter reasons

Tier keys deliberately match what `upsert_scan` maps into `tier1_count..filtered_count`.

| Key | Meaning | Rule outcome |
|---|---|---|
| `Tier 1` | **Trigger** — a trade plan is issued | R1–R7 all pass |
| `Tier 2` | **Watch** — leader in trend, pullback in progress, no trigger yet; or a valid setup blocked by the regime gate (`regime_blocked: true`, informational levels only) | R2–R4 pass, R5 not met (or R1 failed) |
| `Tier 3` | **Extended** — leader in trend, no pullback yet | R2–R3 pass, R4 not met |
| `filtered` | Everything else, with `filter_reason` | first failing rule or gate |

Filter reasons: `no_price_data`, `insufficient_history`, `data_quality`, `illiquid`, `not_leader`, `trend_fail`, `stop_too_wide`, `correlated`, `size_zero`, `signal_cap`, `compute_error`.

## 6. Trade plan and execution assumption

`entry_ref` is the last completed bar's close. The scan runs premarket, so the plan is for **that morning's session**. Every plan carries a **chase limit** (`entry_ref + 0.5·ATR`) and an **invalidation** level (the stop). Human rule: skip the trade if the open is above the chase limit or at/below the stop.

Share counts use an assumed equity (`--equity`, or `SECTOR_SWING_EQUITY`, default a **placeholder** $50,000) and 1% risk per trade; both are recorded in `data_provenance`. Per-share levels are the durable data — a UI should recompute shares from them for the viewer's real equity.

## 7. Storage

Persists through the existing `ScanRepository.upsert_scan(strategy_id="sector_etf_swing", universe_id="sector_etfs")` — **no new tables, no API changes**. The unique key is `(scan_date, strategy_id, universe_id)`; same-day reruns replace the run. See [DATA_MODEL.md](DATA_MODEL.md#sector-etf-swing-ticker_resultsdetail) for the payload.

Exports (via `config.scan_output_paths`) go to `data/output/sector_etf_swing/sector_etfs/`: `scan_results.csv`, `report.json`, `summary.md`. Dry runs go to `data/output/dry_run/`.

Because `_build_report_dict` rebuilds the API report from run columns plus `metadata`, only the `market_regime` dict and each ticker's `detail` reach API consumers in full. The fields a UI needs (`as_of_price`, `data_freshness`, `regime_gate_passed`, `schema_version`) are therefore denormalised into `market_regime` and each `detail`. The full `data_provenance` block (equity, risk %, expected session, rule-constant hash) is in `scan_runs.metadata`.

The strategy is intentionally **not** in `history/actionable.py`, `digest/command_center.py`, or the digests, so it does not appear in Command Center, Today's Priorities, cross-strategy ticker history, or emails (spec Phase 4, needs explicit approval). Side effect: while Streamlit is still running, `sector_etfs` shows in its universe dropdown for Launchpad and Lynch with "no scan".

## 8. Running and scheduling

```bash
docker exec quant-hub-dev quant-sector-swing --dry-run          # synthetic data, persists nothing
docker exec quant-hub-dev quant-sector-swing --force-refresh    # what cron runs
docker exec quant-hub-dev quant-hub status                      # shows the run + sector-swing-daily job
curl -s "http://localhost:5020/api/scans/latest?strategy_id=sector_etf_swing&universe_id=sector_etfs"
```

Flags: `--universe`, `--dry-run`, `--no-cache`, `--force-refresh`, `--allow-stale`, `--equity`, `--risk-pct`, `--report {json,md,both}`. Exit code is non-zero on stale/missing data.

**Cron** (`docker/crontab`, America/New_York): `20 5 * * 1-5 ... quant-sector-swing --force-refresh` — after the Launchpad scans (05:00–05:15) and before the 05:30 digest. The crontab is baked into the image: rebuild/redeploy the container after changing it. The new CLI entry point (`pyproject.toml`) also needs a rebuild (or `pip install -e .`) before `quant-sector-swing` exists on `PATH`; until then use `python -m quant_hub.cli.sector_swing`. Run in stage for about a week before enabling in prod.

`docker/jobs.yaml` is a reference copy only; it was already out of date (weekday 17:xx times) when this scanner was added.

## 9. React page

The UI is the React frontend at **`/swing`** ("Sector Swing" in the sidebar). The Streamlit dashboard is being decommissioned, so no Streamlit tab was built (spec Phase 1b dropped); `dashboard/` is untouched.

It reads the existing generic endpoints (`/scans/latest?strategy_id=sector_etf_swing&universe_id=sector_etfs`, then `/scans/{id}/report`) — no API changes. Sections:

- **Help and plain-English layer** — a *How to read this page* panel (four steps, tier meanings, the 7 checks, a glossary of RS / ADX / ATR / R / chase limit; open on first visit, remembered in `localStorage`); a coloured **headline** generated from the payload (`swingHeadline` in `lib/swing.ts`: plans ready / leaders being watched / "no trade today" with the reason / market filter off); a chip legend under the ranked table. All wording lives in `lib/swing.ts` (`SWING_RULES`, `SWING_GLOSSARY`, `SWING_TIER_HELP`) so it can be edited in one place.
- **Status banner** — regime gate PASS/FAIL with SPY vs SMA50/SMA200, the price as-of date and data freshness. A warning appears if the scan ran on non-fresh data or the as-of date is more than 4 days old.
- **Trade plans** — one card per Tier 1 setup with an **In plain English** sentence, captioned figures (entry ref, stop and × daily move, 2R target, chase limit, shares, money at risk), a *before the open / after entering* checklist (the R8 exit guidance: sell half at 2R, trail below EMA10, 10-day time stop), and a price ladder (stop / entry / chase / target plus EMA10, EMA20, SMA50 from the stored indicator snapshot). An expandable "Why it qualifies" lists every rule result.
- **Sizing inputs** — equity and risk %, kept in this browser's `localStorage` (never sent anywhere). **Share counts are recomputed client-side** from each plan's per-share risk with the same rule as the backend (`floor(min(equity·risk/R, equity·30%/entry))`); the scan's own share count is only a placeholder. The 30% cap is a constant in `frontend/src/lib/swing.ts` mirroring `SwingParams.max_position_pct` (it is not in the payload).
- **Watchlist** — Tier 2. Regime-blocked setups show their levels as informational only.
- **All ETFs, ranked** — RS rank, RS score, 63d/126d returns, ADX, per-rule chips (green pass / red fail / grey not evaluated) and the outcome or filter reason.

There is no candlestick chart: the API has no price-history endpoint, so the ladder is drawn from stored levels. A `GET /prices/{ticker}` endpoint plus a chart library is the follow-up if you want candles.

The existing *Recent Scans* table links sector-swing rows to `/swing` (the universe explorer only understands Launchpad/Lynch tiers). The strategy is still absent from Today's Priorities / Command Center until Phase 4.

Frontend checks: `docker exec quant-hub-frontend-dev npx tsc -b` and `npm run lint`. The frontend has no unit-test runner; behaviour was checked by server-rendering the real components against a real scan and a synthetic one covering trigger / watch / regime-blocked / stale / empty states, and by comparing the TypeScript sizing function to the Python one over a 180-case grid.

**Deployment note:** `docker-compose.prod.yml` has no frontend service, so today `/swing` exists on the dev stack only. It becomes reachable in prod when the React frontend is deployed there (part of retiring Streamlit).

## 10. Configuration and source code

| Concern | File |
|---|---|
| Constants, tiers, reasons, `SwingParams`, equity resolution | `src/quant_hub/sector_swing/config.py` |
| Wilder ADX | `sector_swing/adx.py` |
| Per-ticker indicators (computed once) | `sector_swing/indicators.py` |
| Expected-session calendar | `sector_swing/calendar.py` |
| Rules R1–R6 (pure) | `sector_swing/rules.py` |
| Sizing R7, trade plan | `sector_swing/sizing.py` |
| Value types | `sector_swing/models.py` |
| Orchestration, freshness, gates | `sector_swing/runner.py` |
| Report dict + markdown | `sector_swing/report.py` |
| Service (job audit, persist, exports) | `src/quant_hub/application/sector_swing_service.py` |
| CLI | `src/quant_hub/cli/sector_swing.py` |
| React page | `frontend/src/components/SectorSwing.tsx` (+ `SwingPlanCard`, `SwingLeadersTable`, `SwingRuleChips`, `PriceLadder`), `frontend/src/lib/swing.ts`, types in `frontend/src/lib/api.ts` |
| Universe | `data/universes.json` (`sector_etfs`, ETF mode, Lynch disabled), `data/universes/sector_etfs.txt` |
| Tests | `tests/unit/test_sector_swing_*.py` |

The universe is `eligibility_mode: etf` with `lynch_enabled: false`, so `quant-launchpad-daily`, `quant-launchpad-all`, and `quant-lynch-all` skip it. A regression test guards this. The scan-rubric and scoring modules (`scoring/`, `factors/`, `filters/`, `regime/`, `strategies/`, `engine/`, `lynch/`, `report/`) are imported read-only at most and were not modified.

## 11. Why a separate pipeline (D1)

This follows the Lynch pattern (own package, own service, own CLI) rather than registering a `StrategyEngine` strategy. This is a documented choice, not an oversight (see NFR review finding 5.3).

- The engine scores single stocks on a 0–100 rubric per ticker. This scanner ranks a small universe **against a benchmark**, applies portfolio-level gates, and emits trade plans.
- Registering a third engine strategy means editing the scan-rubric boundary: `engine/runner.py` sets `load_fundamentals = spec.id not in ("launchpad",)` (a new strategy would download Yahoo fundamentals), `report/builder.py` branches on `strategy_id == "launchpad"`, and the strategy registry is hard-coded.

The weaknesses the NFR review names for the Lynch pipeline are avoided here: failures are isolated per ticker, and indicators are computed once per ticker and handed to the rules instead of being recomputed.

## 12. Deviations from the spec

- **`signal_cap` filter reason** added: with 4 leaders and a cap of 3 plans, a fourth fully qualified setup otherwise had no reason in the vocabulary.
- **Provenance denormalisation** into `market_regime` / `detail` (Section 7), because `data_provenance` is stored but not returned by the API.
- **`sector_swing/models.py`** added to the file layout to hold shared value types and avoid a runner ↔ report import cycle.
- **Streamlit tab (Phase 1b) dropped**: the dashboard is being decommissioned, so the React page (Phase 1c) is the UI. It uses the shared `Table` primitives for the 16-row table rather than TanStack Table, and shows a levels ladder instead of a candlestick chart (no price API).
- `--dry-run` skips the freshness gate and writes to `data/output/dry_run/`.
- Service tests use constructor injection with fakes; `tests/unit/test_lynch_service.py` (cited by the spec) is a single source-inspection test, not a fake-repo pattern.

## 13. Known limitations

- Yahoo is the only price source; a bad or late Yahoo bar is caught by the freshness and quality gates but not cross-checked.
- Some ETFs have short histories (XLC began 2018; VNQ vs XLRE differ) and the fixed ETF list is not point-in-time. These matter for Phase 3 backtests, not for the daily scan.
- The regime gate is SPY-trend only (no breadth confirmation).
- Open-position awareness, the concurrent-position limit, and the weekly loss limit are Phase 2.
- The NYSE holiday list must be extended before 2029.
