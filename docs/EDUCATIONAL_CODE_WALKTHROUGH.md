The simplest core path is a **Launchpad scan of one ticker with `--cache`**. Lynch and ML are extra loops. Launchpad **does not** fetch fundamentals.

Imagine this command:

```bash
quant-launchpad --tickers NVDA --cache --report json
```

`NVDA` becomes a row of daily prices, a score, then a Postgres row.

---

## Map of the trip (one ticker)

```
CLI  →  Universe  →  Yahoo/cache  →  ScanContext  →  Engine
  →  eligibility  →  5 factors  →  aggregate + tier  →  report  →  Postgres
```

Libraries along the way:

| Library | Used? | What it does here |
|---------|--------|-------------------|
| **yfinance** | yes | Downloads daily Open/High/Low/Close/Volume from Yahoo |
| **pandas** | yes | Tables of prices; filter, concat, `.iloc[-1]`, `.tail(30)` |
| **pyarrow** (via pandas) | yes | Read/write `.parquet` cache files |
| **numpy** | yes | Indicators (EMA, ATR) and NaN/finite checks |
| **psycopg** | yes | Talks to Postgres with SQL |
| **SQLAlchemy** | **no** | This project writes SQL by hand |

---

## Step 0 — You press the button

**File:** `src/quant_hub/cli/launchpad.py`  
**Function:** `main()`

```16:57:src/quant_hub/cli/launchpad.py
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Launchpad scan")
    # ...
    use_cache = args.cache and not args.force_refresh
    persist = not args.no_persist

    service = ScanService(strategy_id="launchpad")
    result = service.run(
        universe_id=args.universe,
        tickers=args.tickers,
        # ...
        use_cache=use_cache,
        persist=persist,
    )
    return result.exit_code()
```

**What Python is doing**

- `argparse` turns `--tickers NVDA --cache` into an object (`args`).
- `list[str] | None` is a **type hint**: “this may be a list of strings, or nothing.” Python does not enforce it at runtime; it is documentation for humans and tools.
- `ScanService(...)` creates an object; `.run(...)` is a **method** (a function attached to that object).

**Libraries:** none of the market/DB libs yet. This file only parses flags and calls the application layer.

---

## Step 1 — Turn “NVDA” into a universe list

**Files / functions**

- `ScanService.run()` in `src/quant_hub/application/scan_service.py`
- `UniverseService.resolve()` in `src/quant_hub/application/universe_service.py`
- `UniverseRegistry.resolve()` in `src/quant_hub/universes/registry.py`
- `_normalize_tickers()` in `src/quant_hub/data/tickers.py`

`--tickers NVDA` wins over `--universe`. The registry uppercases, validates, and returns `("custom", ["NVDA"])`.

```17:28:src/quant_hub/data/tickers.py
def _normalize_tickers(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in symbols:
        symbol = raw.strip().upper()
        if not symbol or symbol in seen:
            continue
        # ...
        out.append(symbol)
    return out
```

**Beginner concepts**

- `set()` = “have I already seen this ticker?” Unique membership is O(1).
- `.strip().upper()` = string methods chained; `" nvda "` becomes `"NVDA"`.
- A **tuple** return `(uid, tickers)` is a common Python pattern: return two values at once.

Then `ScanService` builds a `StrategyEngine` and calls `engine.run()`.

---

## Step 2 — Load prices (Yahoo + Parquet)

**File:** `src/quant_hub/engine/runner.py` → `StrategyEngine.run()`

Launchpad **skips fundamentals**:

```36:46:src/quant_hub/engine/runner.py
        load_fundamentals = self.spec.id not in ("launchpad",)
        ctx = self._context or ScanContext.from_universe(
            tickers=self.tickers,
            use_cache=self.use_cache,
            load_fundamentals=load_fundamentals,
        )
```

`"launchpad" not in ("launchpad",)` is False, so `load_fundamentals` is False. Only prices.

**File:** `src/quant_hub/engine/context.py` → `ScanContext.from_universe()`

It always also downloads **SPY** and sector ETFs (for regime and relative strength), then slices NVDA out:

```109:145:src/quant_hub/engine/context.py
        download_tickers = sorted(set(universe) | set(ALL_SECTOR_ETFS) | {BENCHMARK_TICKER})
        # ...
        prices = download_prices(download_tickers, use_cache=use_cache)
        spy_df = ticker_df(prices, BENCHMARK_TICKER)
        # ...
        for ticker in universe:
            df = ticker_df(prices, ticker)
            if df is not None and not df.empty:
                stock_dfs[ticker] = df
```

**Beginner concepts**

- `@classmethod` on `from_universe` = “construct a `ScanContext` without already having one.” Factory method.
- `set(a) | set(b)` = **set union**. NVDA + XLK + SPY, etc., no duplicates.
- `dataclass` = a class that is mostly “a bag of fields” (`universe`, `stock_dfs`, `spy_df`).
- `ticker_df` filters the big table: `prices[prices["ticker"] == ticker]` — boolean indexing in pandas.

**Libraries:** pandas (`DataFrame` of all tickers stacked). Download is not in this file.

---

## Step 3 — Cache vs Yahoo (the actual fetch)

**Re-export:** `src/quant_hub/infrastructure/market/yfinance_provider.py` just imports `download_prices`.

**Real work:** `src/quant_hub/infrastructure/market/yfinance_prices.py`

### 3a. Split fresh vs stale

```78:90:src/quant_hub/infrastructure/market/yfinance_prices.py
def download_prices(
    tickers: list[str],
    *,
    use_cache: bool = False,
    lookback_days: int = LOOKBACK_DAYS,
    cache: ParquetCache | None = None,
) -> pd.DataFrame:
    tickers = sorted(set(tickers))
    cache = cache or ParquetCache()
    cached_tickers, stale_tickers = cache.partition(
        tickers, use_cache=use_cache, max_bar_age_days=5
    )
```

The `*` in the signature means everything after it is **keyword-only**: you must write `use_cache=True`, not a positional True.

**File:** `src/quant_hub/infrastructure/cache/parquet_cache.py`

- `path_for("NVDA")` → `data/cache/prices/1d/2y/NVDA.parquet` (`PRICE_CACHE_SUBDIR` in `config.py`).
- `is_fresh()`: file exists, younger than 24h TTL, last bar not incomplete, last bar not older than 5 days.
- `partition()`: two lists — **hits** (read from disk) vs **misses** (call Yahoo).

```100:108:src/quant_hub/infrastructure/cache/parquet_cache.py
        if not use_cache:
            return [], tickers   # everything is "stale" → fetch all
```

Without `--cache`, **every** ticker is fetched.

### 3b. Read Parquet (cache hit)

```56:70:src/quant_hub/infrastructure/cache/parquet_cache.py
    def read(self, ticker: str) -> pd.DataFrame | None:
        df = pd.read_parquet(path)   # pandas + pyarrow
        df["Date"] = pd.to_datetime(df["Date"])
        df = drop_incomplete_ohlcv_bars(df)
        df["ticker"] = ticker.upper()
        return df
```

**pandas `read_parquet`:** load a columnar file into a DataFrame (Date, Open, High, Low, Close, Volume). Faster and smaller than CSV.

### 3c. Yahoo download (cache miss)

```48:56:src/quant_hub/infrastructure/market/yfinance_prices.py
def _download_chunk(tickers: list[str], start: str) -> pd.DataFrame:
    raw = yf.download(
        tickers,
        start=start,
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
```

**yfinance** is a wrapper around Yahoo’s HTTP API. One call can return many tickers. Columns are often a **MultiIndex** (`NVDA` → `Close`). `_finalize_ohlcv` flattens that into one row per day with a `ticker` column.

Then each ticker is written:

```104:107:src/quant_hub/infrastructure/market/yfinance_prices.py
            for ticker in chunk:
                sub = chunk_df[chunk_df["ticker"] == ticker]
                if not sub.empty:
                    cache.write(ticker, sub)
```

### 3d. Atomic write + lock (cache write)

```88:98:src/quant_hub/infrastructure/cache/parquet_cache.py
        with open(lock_path, "a", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                out.to_parquet(tmp_path, index=False)
                os.replace(tmp_path, path)
            finally:
                tmp_path.unlink(missing_ok=True)
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
```

**Beginner concepts (this is the richest Python in the cache)**

- **Context manager** (`with open(...) as lock_file`): enter = open file; exit = close it even if something fails.
- **`fcntl.flock`**: OS lock so two scans don’t write `NVDA.parquet` at once.
- **`try` / `finally`**: `finally` always runs (unlock, delete `.tmp`).
- **Write-then-replace:** write `NVDA.parquet.tmp`, then `os.replace` so readers never see a half-written file.
- `df.to_parquet(...)` uses **pyarrow** under pandas.

Result of this step: one tall DataFrame of all tickers, including NVDA’s OHLCV.

---

## Step 4 — Market regime (SPY, not NVDA)

Still in `ScanContext.from_universe`:

- `compute_market_regime(spy_df)` in `src/quant_hub/regime/market.py`

Launchpad **does not** multiply NVDA’s score by regime (`regime_mode="none"` in the spec). Regime is stored for the report/dashboard.

---

## Step 5 — Score NVDA (the engine loop)

**File:** `src/quant_hub/engine/runner.py` — `StrategyEngine.run()` then `_evaluate_filters()`

**Recipe** (what Launchpad is): `src/quant_hub/strategies/launchpad/spec.py` → `LAUNCHPAD_STRATEGY`

### 5a. Eligibility filter

```142:147:src/quant_hub/engine/runner.py
    def _evaluate_filters(self, ctx: ScanContext, ticker: str) -> FilterResult:
        for filt in self.spec.filters:
            result = filt.evaluate(ctx, ticker)
            if not result.passed:
                return result
        return FilterResult(passed=True, reason="eligible", checks=[])
```

**File:** `LaunchpadEligibilityFilter.evaluate()` in `src/quant_hub/strategies/launchpad/filters.py`  
→ **`launchpad_eligibility_detail(df)`** in `src/quant_hub/scoring/launchpad.py`

Pandas on NVDA’s frame:

- enough history days
- last `Close` ≥ $10
- 30-day average `Volume` high enough
- price above 200-day EMA
- near EMA50 or a support shelf

Example of pandas:

```python
price = float(df["Close"].iloc[-1])   # last row of Close
avg_vol_30d = float(df["Volume"].tail(30).mean())
```

- `.iloc[-1]` = last row (integer position).
- `.tail(30)` = last 30 rows.
- `.mean()` = average.

If any check fails, NVDA is still kept (`scorable_tickers`) but `eligible=False`. Scores still compute; tier will be `"filtered"`.

### 5b. Five factors (ticker pass)

Each factor is a tiny class in `src/quant_hub/factors/launchpad.py` that calls a function in `scoring/launchpad.py`:

| Factor class | Scoring function | Max pts | Meaning |
|--------------|------------------|---------|---------|
| `SqueezeIntensityFactor` | `score_squeeze_intensity` | 40 | Bollinger vs Keltner squeeze |
| `VolumeVacuumDepthFactor` | `score_volume_vacuum_depth` | 30 | Volume dry-up |
| `TightnessPercentileFactor` | `score_tightness_percentile` | 15 | Tight daily ranges |
| `TrendProximityMatchFactor` | `score_trend_proximity_match` | 15 | Trend + vs SPY |
| `MacdZeroLineFactor` | `score_macd_zero_line` | 25 | Ignition gate (not in the 100-pt sum) |

Example squeeze (pandas + numpy indicators from `src/quant_hub/indicators.py`):

```347:371:src/quant_hub/scoring/launchpad.py
def score_squeeze_intensity(df: pd.DataFrame) -> tuple[float, dict]:
    close = df["Close"]
    upper_bb, _, lower_bb = bollinger_bands(close, window=20, num_std=2.0)
    # ... compare BB width vs Keltner width ...
    if squeeze_ratio < 0.90:
        return 40.0, details
```

**`tuple[float, dict]`** = returns two things: a number and a details dict (for the report JSON).

**`make_factor_result`** in `src/quant_hub/factors/base.py` wraps that into a `FactorResult` dataclass (`src/quant_hub/engine/types.py`).

The engine stores them on `TickerResult.factors`.

### 5c. Add up + assign tier

**`aggregate_launchpad_ticker()`** in `src/quant_hub/strategies/launchpad/aggregate.py`

```28:38:src/quant_hub/strategies/launchpad/aggregate.py
    raw = sum(
        fr.score for name, fr in ticker.factors.items() if name in LAUNCHPAD_SCORE_FACTORS
    )
```

That line is a **generator expression** (like a list comprehension without building a list): “sum every factor score whose name is in the four scoring factors.”

Then raw → 0–100 `normalized_score` = `final_score`.

**`assign_tier()`** in `src/quant_hub/strategies/launchpad/tiers.py`

- not eligible → `"filtered"`
- high score **and** MACD 25 pts → `"Tier 1"`
- high enough score → `"Tier 2"`
- else → `"Tier 3"`

`StrategyEngine.run()` returns a `ScanResult` (list of `TickerResult`).

---

## Step 6 — Turn objects into a report dict

Back in `ScanService.run()` (`scan_service.py`):

1. `scan_result.to_dataframe()` → `scan_result_to_dataframe()` in `src/quant_hub/engine/export.py`  
   **List comprehension:** `rows = [t.to_row_dict() for t in result.tickers]` then `pd.DataFrame(rows)`. CSV is written here.

2. `build_scan_report()` in `src/quant_hub/report/builder.py`  
   Per ticker, `build_ticker_report()` packs eligibility, scores, tier into a nested **dict** (the JSON shape).

3. Optional JSON/Markdown files via `src/quant_hub/report/export.py`.

Postgres does **not** store the DataFrame. It stores this report dict.

---

## Step 7 — Save to PostgreSQL

**File:** `src/quant_hub/infrastructure/postgres/repository.py`  
**Function:** `ScanRepository.upsert_scan()`

Called as:

```124:130:src/quant_hub/application/scan_service.py
            if persist:
                run_id = self.scan_repo.upsert_scan(
                    scan_date=scan_date,
                    strategy_id=self.strategy_id,
                    universe_id=resolved_id,
                    report=scan_report,
                )
```

**Connection:** `get_connection()` in `src/quant_hub/infrastructure/postgres/connection.py`

```16:22:src/quant_hub/infrastructure/postgres/connection.py
@contextmanager
def get_connection(*, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(get_connection_url())
    try:
        yield conn
    finally:
        conn.close()
```

**Beginner concepts**

- `@contextmanager` + `yield` = you can write `with get_connection() as conn:`. Enter = connect; after the block = `finally` closes.
- **psycopg** (v3): Python driver. `cur.execute("SELECT ...", (params,))` — `%s` placeholders (not f-strings) to avoid SQL injection.
- **No SQLAlchemy** ORM. Tables are defined in `schema.sql`.

**What `upsert_scan` does**

1. `INSERT INTO scan_runs ... ON CONFLICT (scan_date, strategy_id, universe_id) DO UPDATE`  
   Same calendar day + Launchpad + same universe **replaces** the previous run. `RETURNING id` gives `run_id`.
2. `DELETE FROM ticker_results WHERE run_id = %s` — wipe old NVDA row for that run.
3. `executemany(INSERT INTO ticker_results ...)` — one row per ticker. NVDA’s full JSON goes in `detail` (`jsonb`).
4. `conn.commit()` — actually save. Without commit, the transaction would roll back when the connection closes.

NVDA’s row columns: `ticker`, `eligible`, `tier`, `final_score`, `filter_reason`, `detail`.

---

## Mental model: one object chain for NVDA

```
"NVDA" (str)
  → Parquet / Yahoo  →  DataFrame of daily bars
  → ScanContext.stock_dfs["NVDA"]
  → TickerResult (eligible, factors, final_score, tier)
  → report["tickers"][i]  (nested dict)
  → ticker_results row in Postgres
```

Dashboard later reads Postgres; it does not re-score unless you run the CLI again.

---

## Mini exercises / questions

Use these without changing code. Prefer reading the files above. Check yourself against the answers in parentheses.

**Path and control flow**

1. If you omit `--cache`, does `ParquetCache.partition` treat NVDA as a hit or a miss? *(Miss: it returns `[], tickers`.)*
2. Why does Launchpad still download SPY when you only pass `--tickers NVDA`? *(Regime + `TrendProximityMatchFactor` need `spy_df`.)*
3. Does Launchpad call `download_fundamentals`? *(No — `load_fundamentals` is False for `launchpad`.)*
4. What happens if Yahoo has no NVDA data? *(Filter reason `no_price_data`; still a `TickerResult`; still persisted if `persist=True`.)*

**Python concepts**

5. In `download_prices(..., *, use_cache=False)`, what does the `*` mean? *(Keyword-only arguments.)*
6. Point to one **context manager** in this path. *( `with get_connection()`, `with open(lock_path)`, `with conn.cursor()`.)*
7. Rewrite `rows = [t.to_row_dict() for t in result.tickers]` as a `for` loop. Same result?
8. What is the difference between `TickerResult` (dataclass instance) and the JSON in `ticker_results.detail`? *(In-memory object vs serialized dict stored in Postgres.)*

**Libraries**

9. Which function calls `yf.download`? *(`_download_chunk` in `yfinance_prices.py`.)*
10. Which function calls `to_parquet` / `read_parquet`? *(`ParquetCache.write` / `read`.)*
11. Why `%s` in SQL instead of f-strings? *(Parameterized queries; user/ticker data must not be interpolated into SQL.)*
12. Is `upsert` an INSERT or an UPDATE? *(Both: insert, or update on unique `(scan_date, strategy_id, universe_id)`.)*

**Scoring**

13. Which four factor **names** go into the 100-pt raw score? *(squeeze, tightness, volume vacuum, trend/proximity — not MACD.)*
14. Can NVDA have a high squeeze score but still be `filtered`? *(Yes — eligibility failed.)*
15. What extra condition does Tier 1 need besides a high normalized score? *(MACD zero-line score ≥ 25.)*

**Hands-on (read-only)**

16. Open `parquet_cache.py` and write in your notebook: TTL hours, max bar age, file name for `AAPL`.
17. Trace `LAUNCHPAD_STRATEGY.filters` and `factor_bindings` in `spec.py`. How many filters vs factors?
18. In `upsert_scan`, find where NVDA’s JSON is built (`json_dumps(ticker)`). What Python type is `ticker` there? *(A dict from the report, not a `TickerResult`.)*

If you can answer 1–4, 9–12, and 13–15 without peeking, you understand this data path. The rest is Python syntax on top of the same story.