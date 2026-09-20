# Spec: Sector-ETF Swing Scanner for Quant Hub (v2, aligned to the repo)

**Status:** Draft v2 — *update 2026-09-20: Phase 1b (Streamlit tab) is dropped because Streamlit is being decommissioned; the React page (Phase 1c) is the UI, without a candle chart (no price API) — see `docs/SECTOR_SWING_SCANNER.md` §9.*
**Target repo/branch:** `jigar3730/quant-hub`, branch `dev` (reviewed at commit `0a71eba`, 2026-09-16)
**Audience:** Claude Code working inside the repo
**Reference prototype:** `sector_etf_scanner.py` (single file, synthetic-data tested only; see Section 13 for what not to copy)

---

## 0. Working rules for the implementer

These come from the repo's own docs and `.claude/skills/`. Follow them.

1. **Docker only.** Never run Postgres, the API, or Streamlit on the host. Check `docker ps -a --filter name=quant-hub` first; if the dev stack is up, `docker exec` into it. To start it, use `./scripts/run_env.sh dev up -d` (never bare `docker compose up`, and never `cp .env.example .env`). Read `.claude/skills/dev-stack/SKILL.md` before touching compose.
2. **Branching.** Branch off `dev`, merge back into `dev`. One PR per phase in Section 12. Do not stack phases.
3. **Baseline tests.** Before changing anything, run `docker exec quant-hub-dev pytest -q` and record the pass count. Re-run after every phase and report before/after. There is no CI (`docs/ARCHITECTURE_GAPS.md` H6), so this is the only regression check.
4. **Lint.** `ruff check` with the repo config (line length 100, py312, rules `E,F,I,UP`).
5. **Do not modify these paths** (they are the repo's scoring/scan-rubric boundary in `.claude/skills/phase-scope-guard/SKILL.md`; treat the rule as binding for this feature too, even though that skill is written for the modernization phases). Importing from them read-only is fine:
   `src/quant_hub/scoring/`, `factors/`, `filters/`, `regime/`, `strategies/`, `engine/`, `lynch/`, `report/`, and every existing **write** method in `infrastructure/postgres/repository.py`.
   Before each commit run `git diff --stat <base>...HEAD` and confirm no forbidden path appears. If one is genuinely needed, stop and ask.
6. **Do not invent.** If a path, table, or function named here does not match what you find, follow the repo and list the deviation in the PR description. Section 14 lists decisions the owner must confirm.
7. **Research tool only.** The README says "This is **not** a trading bot." Nothing here places orders or connects to a broker, and nothing should imply guaranteed or targeted returns. Reuse `render_disclaimer()` in any UI.

## 1. Purpose

Add a new scanner to Quant Hub that finds **high-probability, asymmetric, multi-day (roughly 3-10 trading days) long swing setups on a tightly controlled universe of sector ETFs**. It favors:

- **market and sector leadership** (trade what is already outperforming SPY),
- **technical entry location** (a pullback that is turning up, not a falling knife),
- **defined risk** (the stop is set before entry and drives position size),
- **good reward-to-risk**, measured in R-multiples.

Output is a ranked set of concrete **trade plans** (reference entry, stop, target, share count) plus a watchlist of leaders that are close to setting up. It is not a prediction system and not a daily-trade system.

## 2. Non-goals (v1)

- No order placement, broker integration, or shorting/options/intraday logic.
- No ML ranking in Phase 1 (a hook is described in Phase 4).
- **No return target.** Do not encode "2% per week" or any return goal anywhere. Performance reporting (Phase 3) shows the distribution of outcomes instead.
- No changes to Launchpad, Lynch, the strategy engine, the regime module, digests, or the Command Center in Phases 1-3.

## 3. What the repo already gives us (verified by reading `dev`)

| Fact | Where | Consequence for this feature |
|---|---|---|
| Daily scans are **premarket cron jobs**: Launchpad scans at 05:00-05:15 ET Mon-Fri, `quant-digest daily` at 05:30 | `docker/crontab` (authoritative; `docker/jobs.yaml` is a reference copy) | Our scan runs after the prior session closes, so the plan is for the session that opens **that same morning**. Schedule ours at **05:20 ET Mon-Fri**, after Launchpad and before the digest. |
| Scans persist through one path: `ScanRepository.upsert_scan(scan_date, strategy_id, universe_id, report)` into `scan_runs` + `ticker_results` (per-ticker `detail JSONB`), unique on `(scan_date, strategy_id, universe_id)`; reruns the same day replace | `infrastructure/postgres/repository.py`, `schema.sql` | Reuse it as-is with `strategy_id="sector_etf_swing"` (16 chars; column is `VARCHAR(32)`). **No new tables in Phase 1.** |
| `upsert_scan` maps non-Lynch tiers from the keys `"Tier 1"`, `"Tier 2"`, `"Tier 3"`, `"filtered"` into `tier1_count..filtered_count` | `_tier_counts_from_report` | Our tier names must use those exact keys (mapping in Section 7). |
| The read-only API is generic: `GET /scans/latest?strategy_id=...`, `/scans/{run_id}/report`, tolerant `ScanReport` / `TickerDetail` models | `api/routers/scans.py`, `api/schemas.py` | Persisting through `upsert_scan` exposes our data to the API and React frontend with **zero API changes**. |
| Lynch is a separate, hand-rolled pipeline (own runner + `LynchScanService` + CLI). `docs/nfr_code_review.md` finding 5.3 flags that as duplication of `engine.StrategyEngine` and says to either consolidate **or document why it stays separate** | `lynch/runner.py`, `application/lynch_service.py` | See D1. We follow the separate-pipeline pattern, and must document why and avoid the specific weaknesses the review names (no per-ticker exception isolation, duplicated indicator computation). |
| `StrategyEngine` is Launchpad-shaped: `load_fundamentals = spec.id not in ("launchpad",)` would make a new strategy download Yahoo fundamentals; `report/builder.py` branches on `strategy_id == "launchpad"`; the registry is hard-coded | `engine/runner.py`, `report/builder.py`, `strategies/registry.py` | Registering a third strategy on the engine means editing forbidden paths. Another reason for D1. |
| `ScanContext.from_universe()` already downloads `ALL_SECTOR_ETFS` + `SPY` on every Launchpad scan | `engine/context.py`, `config.py` | These ETFs are already in the price cache. Our default universe should be the same set. |
| `ALL_SECTOR_ETFS` = `IGV, ITA, KRE, SOXX, VNQ, XBI, XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY` (16 tickers) | `config.py` (`SECTOR_TO_ETF`, `INDUSTRY_TO_ETF`) | Default universe (differs from the prototype list; see Section 13). |
| Universes are defined in `data/universes.json` + `data/universes/*.txt`; a universe may set `"eligibility_mode": "etf"` and `"lynch_enabled": false`; `list_universe_ids(strategy="launchpad")` skips ETF-mode and `strategy="lynch"` skips `lynch_enabled=false`; `quant-launchpad-daily` also skips ETF-mode explicitly | `universes/registry.py`, `universes/batch.py`, `cli/launchpad_daily.py` | A new `sector_etfs` universe in ETF mode with Lynch disabled will not leak into existing batch jobs. Add a regression test for that. |
| Prices: Yahoo only, via `download_prices(tickers, use_cache=...)`; long DataFrame with columns `Date, Open, High, Low, Close, Volume, ticker`; `auto_adjust=True` (adjusted OHLC); per-ticker parquet cache; ~252 trading days default lookback; on `dev` the download has a 30s timeout and returns an empty frame on failure instead of raising | `infrastructure/market/yfinance_prices.py`, `infrastructure/cache/parquet_cache.py` | Missing tickers must be handled as `no_price_data`. Cache freshness is loose (see Section 6). |
| Shared helpers: `engine.context.ticker_df`, `synthetic_prices`; `data.quality` (`validate_ohlcv`, `max_bar_date`, `has_price_spike`); `data.provenance.build_data_provenance`; `config.scan_output_paths`; `serialization.json_util`; `indicators` (`sma`, `ema`, `atr`, `return_over_days`); `regime.market.regime_detail` | as listed | Reuse them. |
| `indicators.atr` is a **simple rolling mean** of true range, not Wilder smoothing; `indicators.ema` uses `min_periods=window`; there is **no ADX** | `indicators.py` | Use the repo's `sma/ema/atr` for consistency. Add ADX in our package (do not edit `indicators.py`). |
| `regime_detail()` now **raises `RuntimeError`** if SPY has too little history for a 200-day SMA, and rounds its outputs to 2 decimals | `regime/market.py` (dev) | Handle the exception (abort run with a clear error). Compute our gate from unrounded values, use `regime_detail` for display fields. |
| Job audit: `JobRunRepository.start_job/finish_job`, shown by `quant-hub status` | `application/*_service.py`, `cli/status.py` | Wrap each run in a job named `sector-swing-daily`. |
| Point-in-time replay tooling exists: 5-year `ParquetCache` (`ML_LABEL_CACHE_SUBDIR`), `ml/backfill_dates.truncate_daily_to_date`, `ScanContext.from_prices` | `config.py`, `ml/backfill_dates.py`, `application/launchpad_backfill_service.py` | Phase 3 reuses these rather than inventing a data path. |
| Production UI is **Streamlit** (`quant-view`, port 5002). The React frontend and FastAPI exist in the **dev** compose stack only (`docker-compose.prod.yml` has no frontend service) | `docker-compose.*.yml`, `docs/MODERNIZATION_AUDIT.md` | The UI plan has two steps (Section 10). |
| `history/actionable.py`, `digest/command_center.py` (`COMMAND_CENTER_STRATEGIES = ("launchpad","lynch")`) ignore unknown strategies | as listed | Our rows will not appear in Command Center, Today's Priorities, or digests. That is intentional for Phases 1-3. |
| Tests: `tests/unit/`, pytest, marker `integration` excluded by default, Postgres-backed tests skip when the DB is unreachable (`pytestmark = skipif(not _postgres_available())`) | `pyproject.toml`, `tests/unit/test_repository.py` | Follow the same patterns. |

## 4. Design decisions

- **D1. Separate pipeline, not a `StrategyEngine` strategy.** The engine scores single stocks on a 0-100 rubric per ticker; this scanner ranks a small universe against a benchmark, applies portfolio-level gates, and emits trade plans. Fitting it to the engine requires edits in forbidden paths (Section 3). Follow the Lynch pattern (own package, own application service, own CLI) and record this rationale in `docs/SECTOR_SWING_SCANNER.md` so it is a documented choice rather than an oversight (NFR review 5.3). Compensate for the review's criticisms: isolate failures **per ticker** (`try/except` -> `compute_error`), and compute each ticker's indicators **once** and pass them to the rules (NFR review 1.1).
- **D2. Persist via `upsert_scan`, no schema change in Phase 1.** The trade plan lives in `ticker_results.detail`. Include `schema_version` in every detail payload and in `data_provenance` (the modernization audit flags the missing version marker as a risk).
- **D3. No YAML config.** Scanners in this repo keep tunables as UPPER_CASE constants (`config.py`, `lynch/config.py`). Put ours in `src/quant_hub/sector_swing/config.py`, with a frozen dataclass for overrides in tests. The universe lives in `data/universes.json`.
- **D4. Account size is not persisted as truth.** Store per-share levels and R distances. Position sizing uses an equity assumption (`--equity` / `SECTOR_SWING_EQUITY`, placeholder default 50,000) recorded in `data_provenance`; UIs recompute share counts from the stored levels.

## 5. Strategy rules (authoritative)

All thresholds are constants in `sector_swing/config.py`. Each rule has an ID that appears in logs and in `detail.eligibility.checks[].rule`. "Bars" are completed daily bars from `ticker_df()`.

### 5.1 Universe and hygiene (rule H)

- Universe `sector_etfs` (Section 8) plus benchmark `SPY` (`config.BENCHMARK_TICKER`).
- A ticker is `no_price_data` if `ticker_df` returns nothing; `insufficient_history` if it has fewer than `MIN_BARS` (210) bars; `data_quality` if `validate_ohlcv(...)` fails (spike, NaN close); `illiquid` if 20-day average dollar volume < `MIN_AVG_DOLLAR_VOLUME` (default 20,000,000) or last close < `ETF_MIN_PRICE`. Do **not** reuse `ETF_MIN_AVG_VOLUME` (share-count based and price-blind); dollar volume is what limits position size.

### 5.2 Rules

| ID | Rule | Definition (defaults) |
|----|------|------------------------|
| R1 | Regime gate | SPY last close > SMA(50) **and** > SMA(200), computed from unrounded `indicators.sma`. Also persist `regime_detail(spy_df)` (label, multiplier, values). When R1 fails: **no Tier 1 and no trade plan**; setups that would qualify are recorded as Tier 2 with `regime_blocked: true`. |
| R2 | Leadership | RS score = 0.5 x (ETF 63d return - SPY 63d return) + 0.5 x (ETF 126d return - SPY 126d return), using `indicators.return_over_days`. Rank descending among tickers that passed hygiene. Eligible leaders: top `TOP_N_LEADERS` (4) **and** RS score > 0 (`REQUIRE_POSITIVE_RS`). Else `not_leader`. |
| R3 | Trend | Close > SMA(50), EMA(20) > SMA(50), ADX(14) >= 20. Else `trend_fail`. |
| R4 | Pullback | Within the last 6 bars (including the signal bar) at least one Low <= EMA(20) x 1.005. Else the ticker is a leader in trend but **extended** (Tier 3). |
| R5 | Trigger | Signal-bar Close > prior bar High **and** Close > EMA(10). If R4 holds but R5 does not: **watch** (Tier 2). |
| R6 | Stop | Stop = min(Low over last 6 bars) - 0.25 x ATR(14) (repo `indicators.atr`). Reject `stop_too_wide` if `entry - stop <= 0` or `> 2.5 x ATR(14)`. |
| R7 | Sizing | `shares = floor(min(equity x risk_pct / (entry - stop), equity x max_position_pct / entry))`. Defaults: risk 1%, max position 30%. Reject `size_zero` if 0. |
| R8 | Exits (guidance in v1, tracked in Phase 2) | Target 1 = entry + 2R (sell half). Remainder trails: close below EMA(10) (default) or chandelier (highest close since entry - 3 x ATR), configurable. Time stop: exit at the close if +1R has not been reached after `MAX_HOLD_DAYS` (10). |

Definitions: `R = entry_ref - stop` per share. ADX uses Wilder smoothing (`alpha = 1/14`) and lives in `sector_swing/adx.py`; it must not modify `quant_hub/indicators.py`.

### 5.3 Entry reference and execution assumption

- `entry_ref` = the last completed bar's Close. The scan runs premarket, so the plan is for **that morning's session**.
- Include in every trade plan a **chase limit** (`entry_ref + 0.5 x ATR`) and an **invalidation** level (`stop`). The human rule: skip the trade if the open is above the chase limit or at/below the stop. Phase 3 simulates exactly this and fills at the session open plus slippage, never at the signal close.

### 5.4 Portfolio-level gates (within one scan; open-position awareness arrives in Phase 2)

- At most `MAX_NEW_SIGNALS` (3) Tier 1 plans per scan, in RS-rank order.
- **Correlation gate:** skip a candidate whose 60-day daily-return correlation (adjusted Close) with an already-selected plan exceeds 0.85 (`correlated`). Phase 2 extends this to open positions.
- Phase 2 only: max 3 concurrent positions; a weekly loss limit (3% of equity) that shows "trading paused" as an advisory flag.

## 6. Data freshness and quality (hard requirements)

The cache and premarket schedule create two ways to scan the wrong bar. Both must be handled.

1. **Stale cache hazard.** `ParquetCache.is_fresh()` accepts a file younger than 24h whose last bar is up to 5 days old, which is far too loose for a swing scanner. Requirement: after loading prices, compare SPY's last bar (`data.quality.max_bar_date`) to the **expected last completed session**. If older, re-download **bypassing the cache** once. If still older, abort: no persist, job status `failed`, non-zero exit, clear log line. Cron should call the CLI with `--force-refresh` (about 17 tickers, cheap).
2. **Expected last completed session.** Before ~16:15 ET on a weekday: the previous trading day; after that: today; weekends roll back to Friday. Holidays: see open question Q5 (small hard-coded NYSE holiday list in `sector_swing/calendar.py` vs a new dependency). Provide `--allow-stale` as an explicit escape hatch that records `data_freshness: "stale_allowed"` in provenance.
3. **Never use a partial bar.** If a bar dated "today" exists before the close, drop it.
4. **Missing benchmark is fatal.** If SPY is missing or `regime_detail` raises, abort (mirrors `ScanContext`).
5. **Partial universe is not fatal.** Missing or bad tickers become `filtered` rows with a reason, and the run reports counts by reason. Record `tickers_fetched/failed` on the job row.
6. **Adjusted prices.** `auto_adjust=True` means historical bars are dividend-adjusted while the latest bar is the actual price. Fine for indicators; note in the docs that plan levels should be checked against live quotes.

## 7. Persistence and report contract

Build a report dict shaped like the existing ones so `upsert_scan`, the API, and the JSON/markdown exports work unchanged.

**Run level (`scan_runs`)**
- `strategy_id = "sector_etf_swing"`, `universe_id = "sector_etfs"`, `scan_date = date.today()` (matches the other services; the price date goes in provenance).
- `scan_summary`: `universe_size`, `eligible_count` (tiers 1-3), `excluded_count`, `tier_counts` (keys below), `actionable_count` (= Tier 1), `filter_breakdown` (reason -> count).
- `market_regime`: `regime_detail(spy_df)` plus `regime_gate_passed` (bool). `regime_multiplier` stays the repo's value.
- `data_provenance` via `build_data_provenance(strategy_id=..., universe_id=..., as_of_price=<SPY last bar>, price_cache=...)` with `extra` including `schema_version`, `equity_assumed`, `risk_pct`, `expected_session`, `data_freshness`, and a hash of the rule constants.

**Tier mapping (must use these keys)**

| Key | Meaning | Rule outcome |
|---|---|---|
| `Tier 1` | **Trigger**: a trade plan is issued | R1-R7 all pass |
| `Tier 2` | **Watch**: leader in trend, pullback in progress, no trigger yet (or regime-blocked trigger) | R2-R4 pass, R5 not met (or R1 failed) |
| `Tier 3` | **Extended**: leader in trend, no pullback yet | R2-R3 pass, R4 not met |
| `filtered` | Everything else, with `filter_reason` | first failing rule or gate |

Filter reason vocabulary: `no_price_data`, `insufficient_history`, `data_quality`, `illiquid`, `not_leader`, `trend_fail`, `stop_too_wide`, `correlated`, `size_zero`, `compute_error`.

**Ticker level (`ticker_results`)**: columns are filled from the report: `eligible` = tiers 1-3; `sector_etf = "SPY"` (what ETF-mode scans use); `final_score` = RS score in percentage points (from `summary.final_adjusted_score`); `filter_reason` from `eligibility.fail_reason`.

**`detail` JSONB (schema_version 1)**: keep the same top-level keys the existing UIs already read, plus our own.

```json
{
  "schema_version": 1,
  "ticker": "XLK",
  "eligible": true,
  "tier": "Tier 1",
  "sector_etf": "SPY",
  "summary": {"final_adjusted_score": 4.21, "rs_score_pct": 4.21, "rs_rank": 1},
  "eligibility": {
    "passed": true, "fail_reason": null, "summary": "...",
    "checks": [{"rule": "R3_trend", "passed": true, "value": 27.4, "threshold": "ADX14 >= 20"}]
  },
  "indicators": {"close": 0, "ema10": 0, "ema20": 0, "sma50": 0, "atr14": 0, "adx14": 0, "pullback_low": 0},
  "trade_plan": {
    "entry_ref": 0, "stop": 0, "risk_per_share": 0, "stop_atr_multiple": 0,
    "target_2r": 0, "chase_limit": 0, "invalidation": 0,
    "shares": 0, "risk_dollars": 0, "position_dollars": 0, "regime_blocked": false
  }
}
```

`trade_plan` is present only for Tier 1 (and for regime-blocked Tier 2 as informational levels). The `eligibility.checks` shape intentionally matches the `EligibilityCheck` type in `frontend/src/lib/api.ts`, so existing audit-trail UI can render it.

Also write the standard exports via `scan_output_paths("sector_etf_swing", "sector_etfs")` (`scan_results.csv`, `report.json`, `summary.md`). Use `export_json_report` (generic). `export_markdown_report` is Launchpad-shaped, so write a small markdown summary in our own package instead of editing `report/`.

## 8. Universe change

- Add `data/universes/sector_etfs.txt` (the 16 tickers above, one per line, same format as the other files) and an entry in `data/universes.json`:
  `"sector_etfs": {"name": "Sector ETFs", "description": "...", "eligibility_mode": "etf", "lynch_enabled": false, "sources": [{"type": "file", "path": "data/universes/sector_etfs.txt"}]}`
- The Dockerfile copies `data/universes.json` and `data/universes/` into the image; prod also copies universe files to `/mnt/fast/quant-data/data` (README). Note this in the PR.
- Side effect: `sector_etfs` will appear in the Streamlit universe dropdown when Launchpad is selected, showing "no scan". Acceptable; mention in docs.

## 9. Code layout and touch points

**New files**

```
src/quant_hub/sector_swing/__init__.py
src/quant_hub/sector_swing/config.py        # constants, STRATEGY_ID, tier keys, reason vocabulary
src/quant_hub/sector_swing/adx.py           # Wilder ADX
src/quant_hub/sector_swing/indicators.py    # compute once per ticker -> frozen dataclass
src/quant_hub/sector_swing/calendar.py      # expected last completed session
src/quant_hub/sector_swing/rules.py         # R1-R6, pure functions
src/quant_hub/sector_swing/sizing.py        # R7
src/quant_hub/sector_swing/runner.py        # orchestration, per-ticker isolation -> report dict
src/quant_hub/sector_swing/report.py        # report dict + markdown summary
src/quant_hub/application/sector_swing_service.py   # mirrors LynchScanService/ScanService
src/quant_hub/cli/sector_swing.py                    # quant-sector-swing
data/universes/sector_etfs.txt
docs/SECTOR_SWING_SCANNER.md
tests/unit/test_sector_swing_*.py
```

**Small additive edits to existing files (all outside the forbidden list)**

- `pyproject.toml`: add `quant-sector-swing = "quant_hub.cli.sector_swing:main"` under `[project.scripts]`.
- `data/universes.json`: the entry above.
- `docker/crontab` and `docker/jobs.yaml`: Section 11.
- `README.md` (CLI and Docs tables), `docs/DATA_MODEL.md` (payload section), `docs/RUNBOOK.md`, `docs/USER_MANUAL.md`.
- Phase 1b only: `dashboard/app.py`, `dashboard/viz/sidebar.py`, `dashboard/viz/labels.py` (`STRATEGY_DISPLAY`), plus new `dashboard/viz/sector_swing_components.py`.
- Optional and tiny: `cli/status.py` loop, so `quant-hub status` lists recent sector-swing scans. Do **not** add the strategy to `STRATEGY_CHOICES` if that also widens the `report/history/show` argparse choices without testing them.

**Must not change:** `history/actionable.py`, `digest/*`, and `digest/command_center.py` in Phases 1-3 (see Phase 4).

## 10. CLI, scheduling, and UI

**CLI `quant-sector-swing`** (modeled on `quant-launchpad-daily`): `--universe` (default `sector_etfs`), `--dry-run` (reuse `engine.context.synthetic_prices`; skip persist and job row), `--no-cache`, `--force-refresh`, `--allow-stale`, `--equity`, `--risk-pct`, `--report {json,md,both}`. Use `setup_logging("scan.log")`. Return a `ServiceRunResult` exit code. Job name `sector-swing-daily`; record fetched/failed counts.

**Cron (`docker/crontab`)**, after the Launchpad scans and before the digest:

```
# 05:20 AM ET — sector ETF swing scan (prior-session close; plan is for today's open)
20 5 * * 1-5 root . /etc/environment; quant-sector-swing --force-refresh >> /app/logs/cron.log 2>&1
```

Mirror it in `docker/jobs.yaml` (update its "last synced" note). The crontab is baked into the image, so the container must be rebuilt/redeployed. Promote dev -> stage -> prod per the README; do not enable in prod until a week of stage runs looks right.

**UI, step 1 (Streamlit, the only production UI).** Add a third strategy option using the same branch pattern as Lynch in `dashboard/app.py` (a dedicated render function, then `render_disclaimer()`, then `st.stop()`), without touching the Launchpad/Lynch code paths. Sections: status banner (as-of price date, regime gate with SPY vs SMA50/200, data-freshness note), leaders table (RS rank, RS score, per-rule pass/fail so it's clear why a leader is not a signal yet), Tier 1 plans (entry ref, stop, 2R target, chase limit, shares, dollars at risk), Tier 2 watchlist, filtered table with reasons, and a per-ticker chart (Plotly is already a dependency) showing candles, EMA10/20, SMA50, and entry/stop/target lines. Sidebar equity and risk-% inputs recompute shares from stored per-share levels. **Escape every ticker/string with `html.escape` if any `unsafe_allow_html` is used** (NFR review 2.2; convention: `_esc()` in `notify/digest_email.py`).

**UI, step 2 (React, dev stack).** Additive only: TS types in `frontend/src/lib/api.ts`, a `SectorSwing` component, a `/swing` route in `App.tsx`, and a nav item in `AppLayout.tsx`. Data comes from the existing `/scans/latest?strategy_id=sector_etf_swing&universe_id=sector_etfs` and `/scans/{run_id}/report`. Verify with `docker exec quant-hub-frontend-dev npx tsc -b` and `npm run lint`. Use TanStack Table like the existing tables; consider Lightweight Charts for price (per the modernization audit).

## 11. Testing and acceptance

Unit tests (pure frames, no network), named `tests/unit/test_sector_swing_*.py`:

- **ADX** against a hand-computed fixture; confirm `indicators.py` is untouched.
- **Each rule** R1-R6 with passing and failing synthetic series, including the exact boundaries (1.005 tolerance, 2.5 ATR stop cap, RS <= 0).
- **Sizing:** risk-limited, cap-limited, zero shares, `entry <= stop`.
- **Tiering:** one fixture per tier and per filter reason; **regime off** yields no Tier 1 and marks blocked setups.
- **No look-ahead:** the scan at date *t* on the full frame equals the scan on the frame truncated at *t* (use `truncate_daily_to_date`).
- **Freshness:** stale SPY triggers a cache-bypass refetch, then a hard fail; partial "today" bar is dropped; `--allow-stale` recorded.
- **Failure isolation:** one ticker raising does not abort the run and becomes `compute_error`; missing SPY aborts.
- **Correlation gate** with two synthetic near-identical series.
- **Service** with fake repos (pattern in `tests/unit/test_lynch_service.py`): job start/finish, persist called once, dry-run persists nothing.
- **Persistence** (Postgres-skip pattern from `test_repository.py`): `upsert_scan` round trip; rerun same day replaces; API `TestClient` returns the run via `/scans/latest?strategy_id=sector_etf_swing` (pattern in `test_api.py`); `ticker_history(actionable_only=False)` does not raise on a sector-swing row.
- **Universe regression:** `sector_etfs` is excluded from `list_universe_ids(strategy="launchpad")` and `strategy="lynch"`, and the default `quant-launchpad-all` universe list is unchanged.

Manual verification in the dev stack (record outputs in the PR):

1. `docker exec quant-hub-dev quant-sector-swing --dry-run`
2. `docker exec quant-hub-dev quant-sector-swing --force-refresh` then `quant-hub status`
3. `curl -s "http://localhost:5020/api/scans/latest?strategy_id=sector_etf_swing&universe_id=sector_etfs"` returns 200
4. `docker exec quant-hub-dev pytest -q`: pass count is baseline plus new tests, with no failures or removed tests
5. `git diff --stat` shows no forbidden path

**Phase 1 definition of done**
- [ ] Baseline test count recorded; after-count reported
- [ ] Scanner runs from the CLI, persists one run, and the API returns it
- [ ] Freshness gate, partial-bar handling, and per-ticker isolation covered by tests
- [ ] Universe added; no change to existing batch universe lists
- [ ] `docs/SECTOR_SWING_SCANNER.md` (pipeline, rules, payload, rationale for D1, ops), README/DATA_MODEL/RUNBOOK updated
- [ ] Cron entry added in `docker/crontab` and `jobs.yaml` (not yet enabled in prod)

## 12. Phases (one PR each, each merged into `dev` before the next branches)

**Phase 1: Scanner, persistence, ops.** Sections 5-9, 11, and the CLI/cron parts of 10. Verifiable through the API and database before any UI exists.

**Phase 1b: Streamlit tab.** UI step 1. Small, isolated, follows the Lynch branch pattern.

**Phase 1c: React page.** UI step 2, additive, dev stack only.

**Phase 2: Paper position tracking.** New table `sector_swing_positions` appended to `schema.sql` (idempotent `CREATE TABLE IF NOT EXISTS`; schema is applied by `quant-hub init-db` at container start, and there is no migration tool, per gap H3), a new repository file `infrastructure/postgres/sector_swing_positions_repository.py` (mirroring `ml_models_repository.py`; **do not edit `repository.py`**), and a service plus CLI subcommands to log fills manually. A daily job updates trailing stops, applies the time stop, enforces max concurrent positions and the weekly loss limit, and extends the correlation gate to open positions. No broker connection.

**Phase 3: Backtest and validation.**
- Point-in-time replay using the 5-year price cache and `truncate_daily_to_date`; **does not write to `scan_runs`** (keeps production history clean).
- Fills at the next session's open with slippage (default 2 bps each way) and the chase/invalidation rules from 5.3.
- Metrics: trade count, win rate, average win and loss in R, expectancy in R, profit factor, CAGR, max drawdown, longest losing streak, time in market, and the **distribution of weekly returns** (median week, share of weeks >= +2%, share of weeks <= -2%).
- Baselines: SPY buy-and-hold and "hold the top-RS ETF, rebalance monthly".
- Walk-forward: rolling 3-year in-sample / 1-year out-of-sample. In-sample is for parameter *sensitivity* (performance across neighborhoods of key parameters), never to pick a single optimum.
- Caveats to print in every report: Yahoo-only data (P1), some ETFs have short histories (XLC began 2018, VNQ vs XLRE differences), and universe membership is not point-in-time (P3, low impact for a fixed ETF list but nonzero). Draw no conclusions from fewer than 100 trades.
- Output files under `data/output/sector_etf_swing/backtests/`.

**Phase 4 (needs explicit owner approval; changes shared behavior).** Add the strategy to `history/actionable.py`, `digest/command_center.py` (`COMMAND_CENTER_STRATEGIES`), `dashboard/viz/labels.py`, and the digest, and optionally expose features to the existing ML pipeline (`ml/features.py`, `ml/training_set.py` branch on `strategy_id`, and forward labels via `signal_outcomes`). This changes the Command Center and Today's Priorities, so do it separately, with tests for the new cross-strategy views.

## 13. Deltas from the prototype (`sector_etf_scanner.py`)

Use the prototype for the rule logic only. Do **not** copy: its `yfinance` loader (use `download_prices` and `ticker_df`), its Wilder-smoothed ATR (use `indicators.atr`; stop distances will differ slightly), its own `ema` (use `indicators.ema`), or its single-file structure. Changes made by this spec:

- Universe is the repo's 16 sector/industry ETFs (`SOXX`, `IGV`, `ITA`, `KRE`, `VNQ`, `XBI`, plus SPDR sectors) instead of the prototype list (`SMH`, `XLRE` are not in the repo set).
- RS must be positive; liquidity is dollar-volume based; history minimum is 210 bars (SMA200 plus RS windows).
- Regime gate uses the repo's `regime_detail` for display and unrounded SMAs for the decision.
- Adds freshness gate, partial-bar handling, per-ticker isolation, correlation gate, time stop, chase limit, tier mapping, persistence, exports, CLI, cron, UI, and docs.
- Not in v1: breadth-based regime confirmation (SPY trend filter only).

## 14. Decisions for the owner (defaults recommended)

| # | Question | Recommended default |
|---|---|---|
| Q1 | UI order | Streamlit tab first (it is the only production UI), React page after |
| Q2 | Equity placeholder and risk % | Keep `50,000` / `1%` as clearly labeled placeholders; set your real values via `SECTOR_SWING_EQUITY` |
| Q3 | Cron time | 05:20 ET Mon-Fri; run in stage for about a week before prod |
| Q4 | Universe | Repo's 16 ETFs; add `SMH`/`XLRE` only if you want them (they overlap `SOXX`/`VNQ`) |
| Q5 | Market calendar for the freshness gate | Small hard-coded NYSE holiday list in `sector_swing/calendar.py`, no new dependency |
| Q6 | Show in Command Center / digest | Not until Phase 4 |
| Q7 | Regime gate | SPY > SMA50 and > SMA200 (as specced) rather than requiring the repo's "strong" label |

## 15. Documentation deliverables

`docs/SECTOR_SWING_SCANNER.md` (mirror the structure of `docs/LYNCH_SCANNER.md`: pipeline, data pull, rules, storage, dashboard mapping, configuration and source files, and the D1 rationale); a README row in both the CLI and Docs tables; a "Sector ETF swing `ticker_results.detail`" section in `docs/DATA_MODEL.md`; the cron/ops entry in `docs/RUNBOOK.md`; a short daily-workflow note in `docs/USER_MANUAL.md`.
