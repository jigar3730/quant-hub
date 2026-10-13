# Non-Functional Requirements (NFR) Code Review

**Scope:** `src/quant_hub/` — 146 Python files, ~18,000 LOC (scoring, factors, filters,
regime, strategies, engine, lynch, report, infrastructure, digest, notify, api, dashboard,
universes, cli, application, data, history, ml, serialization).

**Method:** Five focused passes, one per NFR category, each grepping for known anti-pattern
signatures across the full tree and then reading every hit in context before counting it as a
finding. Grep hits that turned out to be correct patterns, negligible-scale, or already
handled were discarded rather than padded into the report. Read-only review — no files were
modified as part of the audit itself.

**Update (2026-09-16):** all 4 Reliability & Concurrency findings below have since been fixed
and covered by new/updated tests (`tests/unit/test_regime.py`, `tests/unit/test_yfinance_prices.py`,
existing Lynch/cache test coverage). Full suite re-verified green (185 passed) after the fixes.
Each fixed finding is marked **Status: Fixed** in its section below.

## Executive Summary

The codebase is in noticeably better shape than an 18k-LOC scanning system typically is on
NFRs that are easy to get wrong: **SQL is fully parameterized** everywhere it's built
dynamically, **every DB connection/cursor and file handle is context-managed**, a **real
connection pool** backs Postgres access (not per-call connections), and **no hardcoded
credentials, `pickle`, or `eval`/`exec`** exist anywhere in `src/`. Resource management in
particular came back almost clean.

The real risk is concentrated in a small number of places, and it clusters around one theme:
**the unattended, cron-driven premarket pipeline has weak failure signaling.** Two HIGH
findings (no timeout on the Yahoo Finance price download; silently-swallowed Lynch metric
fetch failures with zero logging) mean the exact pipeline that produces the daily Launchpad
digest can hang or silently degrade with no operator ever seeing a log line about it. A third
HIGH finding is a real, measurable performance cost: the same EMA50/EMA200/ATR indicators are
computed twice per ticker on every scan. A fourth HIGH finding is a maintainability risk in
the Lynch scanner's preset-dispatch logic (deep nesting, copy-pasted branches).

Everything else — the API's missing auth, the connection-pool singleton race, the dashboard's
unescaped HTML, the duplicated Lynch/Launchpad orchestration — is real but lower urgency:
either narrow-window, low-practical-risk, or a design-level observation rather than an active
bug.

**14 findings total: 4 High, 6 Medium, 4 Low.**

| Category | High | Medium | Low |
|---|---|---|---|
| Performance & Memory | 1 | 1 | 0 |
| Security | 0 | 1 | 2 |
| Reliability & Concurrency | 2 | 1 | 1 |
| Resource Management | 0 | 1 | 0 |
| Maintainability | 1 | 2 | 1 |

**Priority order if addressing incrementally:** the two Reliability HIGHs (yfinance timeout,
Lynch metric logging) are the cheapest fixes with the highest operational payoff — both are
small, localized diffs that close a real "silent failure in an unattended job" gap. The
Performance HIGH (duplicate EMA/ATR computation) is the next-best return: one shared cache
object touching two functions, measurable win on every scan. The Maintainability HIGH
(`lynch/runner.py` preset dispatch) is worth doing opportunistically the next time that file is
touched, not urgently on its own.

---

## Defect Inventory Table

| Severity | Category | File:Line | Description |
|---|---|---|---|
| High | Performance & Memory | `scoring/launchpad.py:228-247`, `:438-448` | EMA50/EMA200/ATR recomputed independently in eligibility check and in `score_trend_proximity_match` for the same ticker on every scan |
| High | Reliability & Concurrency | `infrastructure/market/yfinance_prices.py:48-56` | `yf.download()` call has no timeout and no exception handling — can hang the unattended premarket cron indefinitely |
| High | Reliability & Concurrency | `lynch/metrics.py:48-58, 61-73, 76-90` | Three metric-fetch helpers swallow all exceptions with zero logging despite a `logger` existing in the file |
| High | Maintainability | `lynch/runner.py:98-193` (`_evaluate`) | Deepest nesting in the repo (depth 7, 95 lines); 3 near-identical copy-pasted preset-dispatch branches |
| Medium | Performance & Memory | `ml/walk_forward.py:91` | `.iterrows()` over the full training-set frame in `apply_ticker_signal_embargo`; `.itertuples()` is a drop-in ~5-10x faster replacement |
| Medium | Security | `api/app.py:17-38`, all routers in `api/routers/` | No authentication on any read-only API endpoint — full scan history is open to anyone who can reach the port |
| Medium | Reliability & Concurrency | `regime/market.py:20-42` (`regime_detail`) | No NaN guard on `sma(close, 200)`; insufficient SPY history silently falls through to `"neutral"` regime instead of erroring |
| Medium | Resource Management | `infrastructure/postgres/connection.py:19-29` (`_get_pool`) | Unlocked lazy singleton; concurrent cold-start requests (FastAPI's threaded path) can race and orphan a live `ConnectionPool` |
| Medium | Maintainability | `application/ml_export_service.py:77-227` (`run`) | 151-line function, nesting depth 5; 4 quality gates hardcoded as sequential branches each touching 2 counters |
| Medium | Maintainability | `lynch/runner.py` vs `engine/runner.py` | Lynch scan orchestration fully duplicates the generic `StrategyEngine` pipeline instead of using it — no shared per-ticker exception isolation |
| Low | Security | `dashboard/viz/navigation.py:66-80` | Ticker/company fields interpolated into raw HTML without `html.escape()`, inconsistent with this repo's own `_esc()` convention in `notify/digest_email.py` |
| Low | Security (informational) | `infrastructure/postgres/repository.py:872-878` (`table_counts`) | Only non-parameterized SQL site in the repo; `table` comes from a fixed 5-tuple, not external input — no action needed |
| Low | Reliability & Concurrency | `infrastructure/cache/parquet_cache.py:46-49` | `is_fresh()` swallows a corrupt-parquet read silently, while `read()` a few lines below logs the identical failure |
| Low | Maintainability | `notify/email.py:40-63` (`send_html_email`) | No logging in the file at all; a missing `EMAIL_TO`/`SMTP_HOST` config silently returns `False` with no diagnostic trace |

---

## Detailed Breakdown

### 1. Performance & Memory

#### 1.1 — HIGH — Duplicate EMA/ATR computation per ticker, every scan
**`src/quant_hub/scoring/launchpad.py:228-247` and `:438-448`**

The eligibility check and `score_trend_proximity_match` each independently compute EMA50,
EMA200, and ATR from the same `stock_df` for the same ticker, on every scan across all 4
daily universes plus weekly coverage scans (hundreds to thousands of tickers per run).

Flawed:
```python
# Eligibility check (lines 228, 245, 247)
ema200 = ema(close, 200)
...
ema50 = ema(close, 50)
atr_val = _atr_value(df)

# score_trend_proximity_match, same ticker, same stock_df, run right after (lines 438-448)
price_ema50 = ema(price_close, 50)
price_ema200 = ema(price_close, 200)
...
atr_val = _atr_value(price_df)
```

Corrected — compute once, thread through:
```python
@dataclass(frozen=True)
class LaunchpadIndicatorCache:
    ema50: pd.Series
    ema200: pd.Series
    atr_val: float | None

def build_indicator_cache(df: pd.DataFrame) -> LaunchpadIndicatorCache:
    close = df["Close"]
    return LaunchpadIndicatorCache(
        ema50=ema(close, 50),
        ema200=ema(close, 200),
        atr_val=_atr_value(df),
    )

# Eligibility and score_trend_proximity_match both accept `cache: LaunchpadIndicatorCache`
# instead of recomputing ema()/_atr_value() internally.
```
This halves the EMA50/EMA200/ATR work on the highest-traffic code path in the repo.

#### 1.2 — MEDIUM — `.iterrows()` in ML walk-forward embargo logic
**`src/quant_hub/ml/walk_forward.py:91`**

`apply_ticker_signal_embargo` runs over the full labeled training-set frame during model
retraining. The per-row logic is inherently sequential (each row's keep/drop decision depends
on a running `blocked_until` per ticker), so it isn't trivially vectorizable — but
`.iterrows()` materializes a `Series` per row, which is unnecessary overhead here.

Flawed:
```python
for idx, row in work.sort_values([ticker_col, "_embargo_date"]).iterrows():
    ticker = str(row[ticker_col])
    scan_ts = row["_embargo_date"]
    ...
```

Corrected:
```python
for row in work.sort_values([ticker_col, "_embargo_date"]).itertuples(index=True):
    idx = row.Index
    ticker = str(getattr(row, ticker_col))
    scan_ts = getattr(row, "_embargo_date")
    if pd.isna(scan_ts):
        continue
    blocked_until = embargo_end_by_ticker.get(ticker)
    if blocked_until is not None and scan_ts <= blocked_until:
        continue
    keep_idx.append(idx)
    embargo_end_by_ticker[ticker] = scan_ts + pd.tseries.offsets.BDay(embargo_trading_days)
```
`~5-10x` faster for this exact access pattern, no behavior change.

**Checked and ruled out:** the `ticker_results` batch insert in `repository.py` already uses
`cur.executemany()` under psycopg 3's pipelining (not the psycopg2 per-row anti-pattern); every
`pd.concat()` call site in the repo builds a list first and concats once (correct pattern);
dashboard `.iterrows()` hits all iterate single-digit-to-~25-row already-capped result sets for
Streamlit rendering — real but negligible.

---

### 2. Security

#### 2.1 — MEDIUM — No authentication on the read-only API
**`src/quant_hub/api/app.py:17-38`, every router under `src/quant_hub/api/routers/`**

All endpoints (`/scans`, `/tickers/{ticker}/history`, `/command-center`, `/outcomes`,
`/models`) have no auth dependency. Anyone who can reach `quant-hub-api-dev:8000` (or its
host-mapped port) can read full scan history. This may be an acceptable deployment assumption
if the service only ever sits behind a private network — but nothing in the code enforces
that; it's currently a deployment assumption, not a code guarantee.

Corrected — a minimal API-key gate:
```python
# src/quant_hub/api/deps.py — add
import os
from fastapi import Header, HTTPException

def require_api_key(x_api_key: str = Header(default="")) -> None:
    expected = os.environ.get("API_KEY", "")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# app.py — gate the routers
app.include_router(scans.router, dependencies=[Depends(require_api_key)])
```

#### 2.2 — LOW — Unescaped ticker/company HTML in the dashboard
**`src/quant_hub/dashboard/viz/navigation.py:66-80`**, consumed via `unsafe_allow_html=True`
in 9 files (e.g. `lynch_components.py:155`).

```python
def ticker_link_html(ticker: str, *, internal: bool = False) -> str:
    symbol = ticker.strip().upper()
    ...
    return f'<a class="ticker-link" href="{href}" target="{target}"{rel}>{symbol}</a>'
```
`symbol` (and elsewhere `company_name`/`sector_etf`) is interpolated into raw HTML with no
escaping. Practical risk is low — tickers come from a controlled universe list, not free-text
input — but it's inconsistent with this same codebase's own convention: `notify/digest_email.py`
wraps every externally-sourced field in `_esc()`/`html.escape()`. Fix to match:
```python
import html

def ticker_link_html(ticker: str, *, internal: bool = False) -> str:
    symbol = html.escape(ticker.strip().upper())
    ...
    return f'<a class="ticker-link" href="{html.escape(href)}" target="{target}"{rel}>{symbol}</a>'
```

#### 2.3 — LOW (informational) — Non-parameterized SQL, but not exploitable
**`src/quant_hub/infrastructure/postgres/repository.py:872-878` (`table_counts`)**
```python
for table in ("scan_runs", "ticker_results", "job_runs", "signal_outcomes", "ml_models"):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
```
`table` iterates a fixed hardcoded tuple, never external input. This is the only
non-parameterized SQL construction site found in the whole repository — noted for completeness,
no action needed.

**Not findings, checked and confirmed safe:** every other dynamic SQL site in `repository.py`
(~12 query builders) uses `clauses.append("col = %s")` with values passed through a parallel
`params` list — real parameterization, not string interpolation. No hardcoded credentials
anywhere (`POSTGRES_PASSWORD` hard-fails with no default in compose). No `pickle`, `eval`,
`exec`, or unsafe `yaml.load` in `src/`. The one `subprocess.call()` (`cli/view.py:22`) uses a
list, not `shell=True`, and is CLI-only. No CORS middleware is configured at all — the secure
default, nothing to misconfigure.

---

### 3. Reliability & Concurrency

#### 3.1 — HIGH — No timeout on the price download every premarket scan depends on
**`src/quant_hub/infrastructure/market/yfinance_prices.py:48-56` (`_download_chunk`)**

**Status: Fixed** — `timeout=30` added, call wrapped in try/except that logs and returns an
empty frame. Covered by `tests/unit/test_yfinance_prices.py`.

```python
def _download_chunk(tickers: list[str], start: str) -> pd.DataFrame:
    raw = yf.download(
        tickers, start=start, auto_adjust=True, progress=False,
        group_by="ticker", threads=True,
    )
```
No timeout, no exception handling, around the call every daily/premarket scan (all 4
universes, feeding the Launchpad digest) depends on. If Yahoo hangs or rate-limits, the
unattended cron step hangs indefinitely — no alerting, no retry, no failure at all, just a
stuck process.

Corrected:
```python
def _download_chunk(tickers: list[str], start: str) -> pd.DataFrame:
    try:
        raw = yf.download(
            tickers, start=start, auto_adjust=True, progress=False,
            group_by="ticker", threads=True, timeout=30,
        )
    except Exception:
        logger.exception("yf.download failed for chunk of %d tickers", len(tickers))
        return pd.DataFrame(columns=["Date", *OHLCV_COLUMNS, "ticker"])
```

#### 3.2 — HIGH — Silently swallowed Lynch metric fetch failures, zero logging
**`src/quant_hub/lynch/metrics.py:48-58, 61-73, 76-90`**

**Status: Fixed** — all 3 helpers now log at `debug` level with `exc_info=True` before
returning `None`.

`_insider_purchases_6m`, `_shares_outstanding_change_yoy`, and
`_revenue_coefficient_of_variation` each swallow every exception with a bare
`except Exception: return None` — and the file has a `logger` (used elsewhere) that these three
functions never call. A Yahoo schema change (e.g. a renamed field) would permanently and
silently zero these metrics for every ticker in an unattended Saturday cron run, with no log
trace to diagnose it.

Flawed (representative of all 3):
```python
def _insider_purchases_6m(ticker: yf.Ticker) -> float | None:
    try:
        ...
    except Exception:
        return None
```

Corrected (apply to all 3 helpers):
```python
def _insider_purchases_6m(ticker: yf.Ticker) -> float | None:
    try:
        ...
    except Exception:
        logger.debug("insider_purchases_6m unavailable for %s", ticker.ticker, exc_info=True)
        return None
```

#### 3.3 — MEDIUM — Regime classification silently falls through on insufficient history
**`src/quant_hub/regime/market.py:20-42` (`regime_detail`)**

**Status: Fixed** — explicit `pd.isna()` guard now raises `RuntimeError`, consistent with this
same file's existing convention for missing benchmark data (`engine/context.py:130`). Covered
by `tests/unit/test_regime.py`.

```python
sma50 = float(sma(close, 50).iloc[-1])
sma200 = float(sma(close, 200).iloc[-1])
...
weak = price < sma200 or dist_from_high > 0.10
```
No guard against `sma(close, 200).iloc[-1]` being NaN when the SPY frame has fewer than 200
rows. `price < nan` evaluates `False` in Python, so an insufficient-history SPY frame silently
falls through to `"neutral"` instead of erroring or warning — a silently-wrong input to Tier 2
suppression for the entire daily scan, with no log line. (The caller in `engine/context.py:129-130`
only guards `spy_df.empty`, not insufficient row count.)

Corrected:
```python
sma50_val = sma(close, 50).iloc[-1]
sma200_val = sma(close, 200).iloc[-1]
if pd.isna(sma50_val) or pd.isna(sma200_val):
    raise RuntimeError(f"Insufficient SPY history for regime classification ({len(close)} rows)")
sma50, sma200 = float(sma50_val), float(sma200_val)
```

#### 3.4 — LOW — Inconsistent logging on corrupt cache read
**`src/quant_hub/infrastructure/cache/parquet_cache.py:46-49` vs `71-73`**

**Status: Fixed** — `is_fresh()` now logs a warning matching `read()`'s existing behavior.

`is_fresh()` swallows a corrupt-parquet read with a bare `except Exception: return False` and no
log line, while `read()` a few lines below logs a warning for the identical failure. Persistent
on-disk corruption is silently treated as "just stale" forever with no signal in logs.

```python
# is_fresh() — no logging
try:
    raw = pd.read_parquet(path)
except Exception:
    return False
```

Corrected:
```python
try:
    raw = pd.read_parquet(path)
except Exception:
    logger.warning("Corrupt cache file for %s; forcing refresh", ticker)
    return False
```

**Not a finding:** no concurrency/shared-mutable-state issues found — no module-level mutable
caches exist in the repo, and the one `ThreadPoolExecutor` use (`lynch/metrics.py:304-312`)
correctly isolates results per-future with no shared write.

---

### 4. Resource Management

#### 4.1 — MEDIUM — Unlocked lazy connection-pool singleton can race under concurrent load
**`src/quant_hub/infrastructure/postgres/connection.py:19-29` (`_get_pool`)**

```python
_pool: ConnectionPool | None = None

def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(get_connection_url(), min_size=1, max_size=10, open=True)
    return _pool
```
FastAPI runs its sync path-operation functions in a worker thread pool, so concurrent requests
genuinely run in different threads of the same process. On a cold process start, two threads
can both observe `_pool is None` and each construct a `ConnectionPool` (each opening real
connections to Postgres); the second assignment wins, and the first pool — holding live DB
connections — is orphaned with nothing to close it. `ConnectionPool` doesn't guarantee prompt
cleanup on GC, so those connections leak until process exit or eventual GC/finalizer reaping.
Narrow window (only a genuine concurrent-first-call race), not a per-request leak, but real.

Corrected:
```python
import threading

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()

def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(get_connection_url(), min_size=1, max_size=10, open=True)
    return _pool
```

**Everything else in this category checked out clean:** all 7 `open(...)` calls in `src/` are
inside `with` blocks; all 36 `get_connection()`/cursor call sites are context-managed; DB access
goes through this real `psycopg_pool.ConnectionPool`, not per-call raw connections, and no
`psycopg.connect()` bypasses it anywhere; the one `ThreadPoolExecutor` is used with `with` and
consumed via `as_completed`; FastAPI's dependency injection shares the same pool per request,
no per-request connection leak; both file-lock cache writers correctly pair
`flock`/`LOCK_UN` and temp-file cleanup inside `try/finally`.

---

### 5. Maintainability

#### 5.1 — HIGH — Deep nesting and copy-pasted preset dispatch
**`src/quant_hub/lynch/runner.py:98-193` (`LynchScannerRunner._evaluate`)**

The single most deeply-nested function in the repo (depth 7, 95 lines). Preset dispatch is a
long `if/elif` chain, 3 of whose branches repeat the identical shape — run a classifier, extend
`all_checks`, set `categories`/`fail_reason` — with copy-pasted structure instead of a shared
pattern. Any change to how a preset's result folds into `all_checks`/`categories` has to be
made, and re-verified, in each of the 3 places.

```python
if self.preset == "fast_grower":
    passed, preset_checks = classify_fast_grower(metrics)
    all_checks.extend(preset_checks)
    if passed:
        categories = ["fast_grower"]
    else:
        fail_reason = "fast_grower_criteria"
elif self.preset == "stalwart":
    passed, preset_checks = classify_stalwart(metrics)
    all_checks.extend(preset_checks)
    if passed:
        categories = ["stalwart"]
    else:
        fail_reason = "stalwart_criteria"
elif self.preset == "asset_play":
    ...  # same shape again
```

Suggested direction — table-driven dispatch for the 3 identical-shape branches (`base` and the
default branch differ enough to stay explicit):
```python
_PRESET_CLASSIFIERS = {
    "fast_grower": classify_fast_grower,
    "stalwart": classify_stalwart,
    "asset_play": classify_asset_play,
}

if self.preset in _PRESET_CLASSIFIERS:
    passed, preset_checks = _PRESET_CLASSIFIERS[self.preset](metrics)
    all_checks.extend(preset_checks)
    categories = [self.preset] if passed else []
    fail_reason = None if passed else f"{self.preset}_criteria"
elif self.preset == "base":
    ...
```

#### 5.2 — MEDIUM — Long function with hardcoded, duplicated quality gates
**`src/quant_hub/application/ml_export_service.py:77-227` (`MlExportService.run`)**

151 lines, nesting depth 5. Four independent quality-gate rules (tier gate, fetch-error gate,
label-status gate, signal-embargo gate) are hardcoded as sequential
`if quality_gate and strategy == "..." and ...: stats.x += 1; run_stats.x += 1; continue` blocks
inside the per-run/per-detail double loop. Adding a 5th gate means touching 3-4 separate spots
correctly.

```python
if quality_gate and strategy == "launchpad" and setups_only:
    tier = detail.get("tier") or ""
    if tier not in LAUNCHPAD_SETUP_TIERS:
        stats.drop_tier += 1
        run_stats.drop_tier += 1
        continue

if quality_gate and strategy == "lynch" and features.get("fetch_error"):
    stats.drop_fetch_incomplete += 1
    run_stats.drop_fetch_incomplete += 1
    continue
```

Suggested direction — a list of `(counter_name, predicate)` gates evaluated in one place:
```python
_ROW_GATES = [
    ("drop_tier", lambda d, f, s: s == "launchpad" and (d.get("tier") or "") not in LAUNCHPAD_SETUP_TIERS),
    ("drop_fetch_incomplete", lambda d, f, s: s == "lynch" and bool(f.get("fetch_error"))),
]

def _gate_reason(detail, features, strategy, *, quality_gate):
    if not quality_gate:
        return None
    return next((name for name, pred in _ROW_GATES if pred(detail, features, strategy)), None)

reason = _gate_reason(detail, features, strategy, quality_gate=quality_gate)
if reason:
    setattr(stats, reason, getattr(stats, reason) + 1)
    setattr(run_stats, reason, getattr(run_stats, reason) + 1)
    continue
```

#### 5.3 — MEDIUM — Architectural duplication: Lynch orchestration vs. the shared strategy engine
**`src/quant_hub/lynch/runner.py` vs `src/quant_hub/engine/runner.py`**

Launchpad's scan orchestration (universe iteration → eligibility filter → factor scoring → tier
assignment) is expressed generically via `engine.StrategyEngine` + `StrategySpec`/factor
bindings (`engine/runner.py:14-148`). Lynch doesn't use this at all — `LynchScannerRunner` is a
fully separate, hand-rolled pipeline duplicating the same conceptual stages (fetch →
filter/classify → score → tier/fail-reason → report) with its own independent implementation. A
capability added to one path has no equivalent on the other unless someone remembers to port it
— notably, `engine/runner.py` has per-ticker `try/except` isolation around factor computation
(`:106-117`) that `_evaluate` has no equivalent of at all.

This is a design-level finding, not a quick fix. Reasonable next step: once the table-driven
cleanup in 5.1 lands, evaluate whether Lynch's preset/category logic could be expressed as a
`StrategySpec` on the shared engine — or, if the domains are different enough to justify staying
separate, document why, so it isn't mistaken for oversight later.

#### 5.4 — LOW — No logging at all in the email-sending path
**`src/quant_hub/notify/email.py:40-63` (`send_html_email`)**

No `import logging` anywhere in this file. When `EmailConfig.from_env()` returns `None`
(missing `EMAIL_TO`/`SMTP_HOST`), the function silently `return False` with no indication of
why. The caller (`digest_service.py`) does log `email_sent=%s` at INFO, but that only reveals
*that* nothing was sent, not whether it was a misconfiguration versus a deliberate skip.

Corrected:
```python
import logging

logger = logging.getLogger(__name__)

def send_html_email(subject: str, html: str, *, config: EmailConfig | None = None) -> bool:
    config = config or EmailConfig.from_env()
    if not config:
        logger.warning("Email not sent: SMTP/EMAIL_TO not configured")
        return False
    ...
```
