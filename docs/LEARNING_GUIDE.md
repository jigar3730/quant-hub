
This is a study guide for **quant-hub**, written for someone new to Python, data science, and ML. You can read it top to bottom, then come back to one module at a time with the files open.

---

# 1. High-level architecture and concept overview

## What it does, in plain English

Quant-hub is a **homework helper for stock research**, not a robot that buys stocks.

Every week it looks at lists of tickers (called **universes**) and asks two questions:

1. **Launchpad (technical):** Does the *price chart* look like a “coiled spring” — tight range, quiet volume, then a hint of ignition?
2. **Lynch (fundamental):** Does the *company* look like a Peter Lynch–style candidate — growth, valuation, balance sheet?

It saves every answer in **PostgreSQL**, shows them on a **Streamlit dashboard**, and emails a **digest**. Later it can ask a third question: *when Launchpad liked a stock in the past, did the price actually go up afterward?* That is the **ML** loop. The model is used to **study and tune** the scanner. It is **not** plugged into the live daily scan yet.

Think of three layers:

| Layer | Everyday analogy |
|--------|------------------|
| Scanners | A checklist you run on each stock |
| Database + dashboard | A notebook of every past checklist |
| ML | Looking back: “when the checklist said yes, what happened next?” |

## Data science / ML concepts it actually uses

| Concept | What it means here | Where |
|---------|-------------------|--------|
| **Data ingestion** | Download daily prices (and Lynch fundamentals) from Yahoo | `yfinance_prices.py`, fundamentals provider |
| **Caching** | Save prices as Parquet so you don’t re-download | `parquet_cache.py` |
| **Feature engineering (rules)** | Turn OHLCV into EMA, ATR, MACD, squeeze ratios, scores | `indicators.py`, `scoring/launchpad.py` |
| **Point-in-time / no lookahead** | When replaying 2023, hide 2024 prices | `launchpad_backfill_service.py`, `truncate_daily_to_date` |
| **Labeling** | “Did it rise ≥ 2% over the next 5/10/20/63 trading days?” | `ml/labels.py` |
| **Tabular features** | Flatten scan JSON into one row of numbers for a model | `ml/features.py` |
| **Supervised classification** | Predict `label_binary` (up enough vs not) with LightGBM | `ml/train.py` |
| **Walk-forward validation** | Train on past weeks, test on later weeks — never shuffle dates | `ml/walk_forward.py` |
| **Leakage control** | Embargo overlapping signals; drop incomplete labels | `training_set.py`, `walk_forward.py` |
| **Backtesting (research)** | Replay Saturday scans historically | `LaunchpadBackfillService` |
| **Not used** | PyTorch, TensorFlow, live model inference, trade execution | — |

## How data moves (ASCII)

```
  universes.json + ticker .txt files
              |
              v
     +------------------+     Yahoo Finance
     |  CLI / cron      |<---- yfinance
     |  quant-launchpad |      (OHLCV bars)
     +--------+---------+
              |
              v
     parquet cache (one file per ticker)
     data/cache/prices/1d/...
              |
              v
     ScanContext  (dict of Pandas DataFrames)
              |
              +-- Launchpad engine: filters + 5 factors + tier
              |
              v
     scan report (Python dict / JSON)
              |
              v
     PostgreSQL
       scan_runs  +  ticker_results.detail (JSONB)
              |
      +-------+--------+------------------+
      |                |                  |
      v                v                  v
  Streamlit        digest email      ML labels
  dashboard                          (forward returns)
                                         |
                                         v
                                   feature Parquet
                                         |
                                         v
                                   LightGBM model
                                   (research only)
```

One ticker’s happy path: **Yahoo → Parquet → DataFrame → scores → JSON → Postgres → (optional) label + model**.

---

# 2. Module and file breakdown (beginner-friendly)

Data formats you will see everywhere:

- **`str`** — ticker like `"NVDA"`
- **`list[str]`** — a universe
- **`pandas.DataFrame`** — spreadsheet in memory (rows = days or tickers)
- **`pandas.Series`** — one column
- **`dict`** — JSON-like nested data (reports, Postgres `detail`)
- **`dataclass`** — a typed “form” (`TickerResult`, `OutcomeRow`)
- **No PyTorch tensors.** LightGBM eats a numeric DataFrame `X` and a Series `y`.

---

### A. Doors into the program (`cli/`)

| File | Purpose | Concepts | Data in → out |
|------|---------|----------|----------------|
| `cli/launchpad.py` | `quant-launchpad` — one universe scan | `argparse`, calling a service | flags → `ScanService.run()` → exit code |
| `cli/launchpad_all.py` / `launchpad_daily.py` | Many universes / weekday job | loops over universe ids | same |
| `cli/lynch.py` / `lynch_all.py` | Fundamental screen | same CLI pattern | flags → `LynchScanService` |
| `cli/ml.py` | `quant-ml` label / export / train / evaluate | subcommands | flags → ML services |
| `cli/backfill.py` | Historical Saturday scans | point-in-time replay | dates → `LaunchpadBackfillService` |
| `cli/view.py` | Starts Streamlit | `subprocess` | none → browser app |
| `cli/status.py` | `quant-hub status`, init-db, ticker history | ops | DB rows → printed text |
| `cli/digest.py`, `universe.py`, `analytics.py` | Email, lists, weekly stats | orchestration | DB → email / stdout |

**Why these files exist:** so humans and cron run *one command* without importing Python modules by hand. `pyproject.toml` maps command names to `main()`.

---

### B. Managers (`application/`)

These files **do not** compute MACD. They **order the work**: resolve universe → run engine → save → log.

| File | Purpose | Concepts | Data in → out |
|------|---------|----------|----------------|
| `scan_service.py` | Live Launchpad orchestrator | service class, persist | tickers → `ScanResult` → CSV/JSON + Postgres |
| `lynch_service.py` | Same for Lynch | same | tickers → Lynch report → Postgres |
| `launchpad_backfill_service.py` | Replay Saturdays without future bars | truncation, resume | long DataFrame → many `upsert_scan` |
| `universe_service.py` | Resolve `--universe` to tickers | thin wrapper | id → `list[str]` |
| `digest_service.py` | Daily/weekly email content | policy + DB reads | scan rows → email payload |
| `ml_label_service.py` | Attach forward returns to old scans | labeling job | `run_id`s → `signal_outcomes` |
| `ml_export_service.py` | Write feature tables | ETL | DB JSON → Parquet |
| `ml_train_service.py` | Train + register model | supervised ML | DataFrame → LightGBM + `ml_models` |
| `ml_evaluate_service.py` | Walk-forward metrics | validation | folds → AUC / top-k returns |
| `ml_cache_service.py` | Warm the 5y price cache | ingestion | tickers → Parquet |

---

### C. The scoring brain

| File / package | Purpose | Concepts | Data in → out |
|----------------|---------|----------|----------------|
| `engine/context.py` | Load all prices into one bag | dataclass, factory `@classmethod` | tickers → `stock_dfs: dict[str, DataFrame]` |
| `engine/runner.py` | Loop tickers: filter → factors → aggregate → tier | strategy pattern | `ScanContext` → `ScanResult` |
| `engine/types.py` | `TickerResult`, `FactorResult` | dataclasses | objects, not tables |
| `strategies/launchpad/spec.py` | Recipe: which filters/factors | composition | static config object |
| `strategies/launchpad/filters.py` | Eligibility gate | boolean checks | DataFrame → `FilterResult` |
| `strategies/launchpad/aggregate.py` | Sum 4 factors → 0–100 score | generator expression | `TickerResult` mutated |
| `strategies/launchpad/tiers.py` | Tier 1/2/3/filtered | if/else rules | scores → `str` |
| `scoring/launchpad.py` | Rubric math | pandas `.iloc`, indicators | OHLCV DataFrame → `(float, dict)` |
| `factors/launchpad.py` | Thin wrappers around scoring fns | one class per factor | DataFrame → `FactorResult` |
| `indicators.py` | SMA, EMA, ATR, MACD, RSI | **vectorized** rolling windows | `Series` → `Series` |
| `filters/eligibility.py` | Shared price/volume gates | thresholds | DataFrame → pass/fail |
| `regime/market.py` | SPY “risk-on/off” label | market context | SPY DataFrame → `MarketRegime` |
| `lynch/` | Fundamental categories, filters, runner | Yahoo fundamentals, not OHLCV scoring | dicts of ratios → passed + score |

**Shapes**

- **In:** DataFrame with columns `Date, Open, High, Low, Close, Volume` — one row per trading day. Typical length ~200–250 days (live) or ~5 years (ML cache).
- **Out:** `TickerResult` then a nested `dict` for the report. Not a tensor.

---

### D. Data in / data out (`data/`, `infrastructure/`)

| File | Purpose | Concepts | Data in → out |
|------|---------|----------|----------------|
| `universes/registry.py` | Read `universes.json`, load `.txt` | JSON, file I/O | files → `list[str]` |
| `data/tickers.py` | Normalize `nvda` → `NVDA` | regex, sets | strings → clean list |
| `infrastructure/market/yfinance_prices.py` | Yahoo download in chunks | `yf.download`, MultiIndex columns | tickers → tall DataFrame |
| `infrastructure/cache/parquet_cache.py` | Disk cache + file lock | Parquet, `fcntl`, atomic write | DataFrame ↔ `.parquet` |
| `data/fundamentals/` | Lynch Yahoo snapshots | cache + compute ratios | Yahoo → dict/DataFrame |
| `infrastructure/postgres/connection.py` | Open/close DB | **context manager**, **psycopg** (not SQLAlchemy) | URL → connection |
| `infrastructure/postgres/schema.sql` | Table definitions | SQL | — |
| `infrastructure/postgres/repository.py` | `upsert_scan` | parameterized SQL, JSONB | report dict → `scan_runs` + `ticker_results` |
| `outcomes_repository.py` / `ml_models_repository.py` | Labels and model registry | same | outcomes / artifacts |

**Shapes**

- Price cache file: one ticker, many rows (time series).
- Combined download: many tickers stacked (`ticker` column).
- Postgres `ticker_results.detail`: **one JSON document per ticker per scan**.

---

### E. Reports, UI, email

| Package | Purpose | Concepts | Data in → out |
|---------|---------|----------|----------------|
| `report/builder.py` | Build analyst JSON | dict assembly | DataFrames + scores → report dict |
| `dashboard/app.py` | Streamlit pages | widgets, session state | Postgres → HTML tables/charts |
| `dashboard/viz/` | Layout, filters, charts | Plotly + Streamlit | DataFrames → UI |
| `digest/` + `notify/` | Email rules + SMTP | templates | DB → email |

---

### F. Machine learning (`ml/`)

| File | Purpose | Concepts | Data in → out |
|------|---------|----------|----------------|
| `labels.py` | Forward return + binary target | time-series labeling, no lookahead | OHLCV DataFrame → `OutcomeRow` |
| `features.py` | JSON → flat numbers | feature extraction | `detail` dict → `dict` row |
| `training_set.py` | SQL join + filters + embargo | dataset construction | DB → `DataFrame` (`X` cols + `label_binary`) |
| `walk_forward.py` | Time splits, purge, embargo | leakage prevention | dates/DataFrame → train/test dates |
| `train.py` | Fit LightGBM | gradient boosting | `X: DataFrame`, `y: Series` → booster |
| `evaluate.py` | AUC, precision, top-k vs score baseline | sklearn metrics | predictions → `EvalMetrics` |
| `constants.py` | Feature names, horizons, statuses | schema versioning | constants |

---

### G. Glue and config

| File | Purpose |
|------|---------|
| `config.py` | Paths, thresholds, cache dirs, `DATABASE_URL` |
| `docker-compose.yml` | Postgres + app containers |
| `docker/crontab` | Weekday scans + Saturday ML labels |
| `data/universes/` | Ticker lists (copy to `/mnt/fast/quant-data/data` for the live container) |
| `docs/` | Operator manuals (good next reading after this guide) |
| `tests/unit/` | pytest — how the authors expect functions to behave |

---

# 3. Line-by-line annotations (representative snippets)

Read these with the real file open. Comments here are teaching comments, not what is already in the repo.

### 3a. CLI type hints and calling a service

```python
# from src/quant_hub/cli/launchpad.py

def main(argv: list[str] | None = None) -> int:
    # list[str] | None  = "a list of strings, OR nothing"
    # -> int            = "this function returns an integer (exit code)"
    # These are TYPE HINTS. Python will still run if you pass the wrong type;
    # they help humans and editors.

    use_cache = args.cache and not args.force_refresh
    # boolean AND / NOT: cache only if --cache and not --force-refresh

    service = ScanService(strategy_id="launchpad")
    # Create an object. strategy_id= is a KEYWORD ARGUMENT (name=value).

    result = service.run(tickers=args.tickers, use_cache=use_cache, persist=persist)
    return result.exit_code()
```

### 3b. Set union and downloading a table (pandas)

```python
# from src/quant_hub/engine/context.py  (ScanContext.from_universe)

download_tickers = sorted(set(universe) | set(ALL_SECTOR_ETFS) | {BENCHMARK_TICKER})
# set(...)           unique items
# |                  UNION (combine sets, drop duplicates)
# {BENCHMARK_TICKER} a set with one item: "SPY"
# sorted(...)        list in A–Z order (stable, easier to debug)

prices = download_prices(download_tickers, use_cache=use_cache)
# prices is a DataFrame, like:
#   Date        Open   High    Low   Close     Volume  ticker
#   2024-01-02  480    485     478   482      40000000 NVDA
#   2024-01-03  ...
# Many tickers stacked. This is "long" or "tidy" format.

sub = prices[prices["ticker"] == ticker].copy()
# prices["ticker"] == ticker
#   → a Series of True/False (one per row). This is a BOOLEAN MASK.
# prices[mask] keeps only True rows. This is vectorized filtering
#   (no Python for-loop over rows — pandas does it in C/NumPy).
# .copy() makes an independent table so later edits don't surprise you.
```

### 3c. Cache write: context manager + try/finally

```python
# from src/quant_hub/infrastructure/cache/parquet_cache.py

with open(lock_path, "a", encoding="utf-8") as lock_file:
    # CONTEXT MANAGER: on indent = file open; leaving the block = file closed
    # even if an error happens.

    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    # Operating-system lock: only one process writes NVDA.parquet at a time.

    try:
        out.to_parquet(tmp_path, index=False)
        # pandas → Parquet (columnar file). index=False = don't save 0,1,2,...
        os.replace(tmp_path, path)
        # Atomic rename: readers never see a half-written file.
    finally:
        # ALWAYS runs — success or crash.
        tmp_path.unlink(missing_ok=True)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
```

There is no `.fit_transform()` in this project. That is a **scikit-learn Pipeline** method (`StandardScaler().fit_transform(X)`). Quant-hub’s “features” are **already numbers inside the scan JSON**. Training just selects columns.

### 3d. Vectorized indicator (this is the DS “wow” moment)

```python
# from src/quant_hub/indicators.py

def ema(series: pd.Series, window: int) -> pd.Series:
    return series.ewm(span=window, adjust=False, min_periods=window).mean()
    # ewm = exponentially weighted moving window
    # You pass the WHOLE Close column. Pandas computes EMA for every day
    # at once (vectorization). Beginner loop would be:
    #   for i in range(len(close)): ema[i] = ...
    # Same idea, much slower and easier to get wrong.

def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    # shift(1) = yesterday's close on today's row. Classic time-series move.
    # This is how you avoid using "today" as if it were "yesterday".
    tr = pd.concat([...], axis=1).max(axis=1)
    # axis=1 means "across columns" (true range = max of 3 formulas).
    return tr.rolling(window, min_periods=window).mean()
    # rolling(14).mean() = 14-day average. First 13 rows are NaN (not enough data).
```

### 3e. Eligibility: `.iloc[-1]` and `.tail(30)`

```python
# from src/quant_hub/scoring/launchpad.py  (launchpad_eligibility_detail)

price = float(df["Close"].iloc[-1])
# .iloc = index by POSITION, not by date label.
# -1 = last row = most recent close.

avg_vol_30d = float(df["Volume"].tail(30).mean())
# last 30 rows, then average. Vectorized mean — not a for-loop.

if price < 10.0:
    return _fail(checks, "price_below_10")
```

`.loc[]` (label-based) is rare on this path; dates are usually filtered with masks (`df[df["Date"] > anchor]`).

### 3f. Generator expression vs list comprehension

```python
# from src/quant_hub/strategies/launchpad/aggregate.py

raw = sum(
    fr.score for name, fr in ticker.factors.items() if name in LAUNCHPAD_SCORE_FACTORS
)
# GENERATOR EXPRESSION: like a list comprehension without building a list.
# Equivalent beginner code:
#   total = 0
#   for name, fr in ticker.factors.items():
#       if name in LAUNCHPAD_SCORE_FACTORS:
#           total += fr.score

# List comprehension (export.py):
rows = [t.to_row_dict() for t in result.tickers]
# "For each TickerResult t, call to_row_dict(), collect into a list"
df = pd.DataFrame(rows)  # list of dicts → table
```

### 3g. Keyword-only arguments and `@classmethod`

```python
# from engine/context.py

@classmethod
def from_universe(cls, *, tickers: list[str] | None = None, use_cache: bool = False) -> ScanContext:
    # @classmethod = decorator. First arg is the CLASS (cls), not an instance (self).
    # You call ScanContext.from_universe(...) without already having a ScanContext.
    # * = everything after must be named: from_universe(tickers=["NVDA"], use_cache=True)
```

### 3h. Labels: no future leak

```python
# from src/quant_hub/ml/labels.py  (compute_forward_outcome)

df["Date"] = pd.to_datetime(df["Date"]).dt.date
# parse strings/timestamps → Python date objects

future = df[df["Date"] > anchor_date]
# STRICTLY AFTER the scan's as-of date. Same-day close is NOT the entry.
# That is the "no lookahead" rule.

path = future.iloc[:horizon_days]["Close"]
# first N trading days after the anchor (iloc slice, not calendar days)

entry = float(path.iloc[0])           # buy at first future close
total = (path.iloc[-1] / entry - 1) * 100   # (conceptually) percent return

label_binary = total >= return_threshold_pct
# True/False target for LightGBM. Default threshold is 2% (config).
```

`rel.cummax()` / `cummin()` in `_forward_path_metrics` are **running** max/min — “highest/lowest the price got *along the path*,” used for max gain and max drawdown.

### 3i. Train/test by time, not `train_test_split` shuffle

```python
# from src/quant_hub/ml/walk_forward.py

train = [d for d in scan_dates if d < split_date]
test = [d for d in scan_dates if d >= split_date]
# Chronological holdout. Random sklearn train_test_split would leak
# because next week's "future" would sit in the training set.

# from ml/train.py
train_data = lgb.Dataset(X, label=y)
booster = lgb.train(merged, train_data, num_boost_round=100)
# LightGBM's fit. Not sklearn's model.fit(X, y), though the idea is the same:
# X = feature table (rows=examples, columns=numbers)
# y = 0/1 labels
```

### 3j. Postgres upsert + context manager

```python
# from connection.py + repository.py

with get_connection() as conn:
    # @contextmanager + yield: connect on enter, conn.close() in finally
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO scan_runs (...) VALUES (%s, %s, ...) ON CONFLICT ... RETURNING id",
            (scan_date, scan_time, strategy_id, ...),
        )
        # %s are PLACEHOLDERS. psycopg fills them safely.
        # Never do f"INSERT ... {ticker}" — that is SQL injection.

        run_id = cur.fetchone()[0]  # first column of the returned row
        cur.executemany("INSERT INTO ticker_results ...", rows)
    conn.commit()  # without this, the transaction is discarded
```

---

# 4. Data science and ML knowledge nuggets

### 1. Pandas DataFrames instead of raw lists / NumPy-only arrays

**Used for:** prices, scan result tables, training frames.

**Why:** OHLCV is **labeled** (Date, ticker, Close). Pandas gives `.groupby`, boolean masks, `.rolling`, and easy CSV/Parquet. A raw NumPy array would be faster for some math but you would constantly track “column 3 is Close.”

**Not used:** Polars (faster modern alternative), PyTorch tensors (for neural nets / GPUs). This problem is **small tabular** data, not images or language.

---

### 2. Vectorized technical indicators (`rolling` / `ewm`) instead of Python loops

**Used in:** `indicators.py` — SMA, EMA, ATR, MACD.

**Why:** One `close.ewm(...).mean()` computes hundreds of days in compiled code. A `for i in range` loop is slower and easy to off-by-one (lookahead bugs).

**Quant pattern:** indicators are **features derived only from past bars** (plus `shift(1)` for previous close). That is the same spirit as “no future information” in ML labels.

---

### 3. LightGBM binary classifier instead of logistic regression or a neural net

**Used in:** `ml/train.py` — `objective: "binary"`, metric AUC.

**Why here:**

- Features are a **handful of numbers** already computed by Launchpad (`LAUNCHPAD_FEATURE_COLUMNS`: final score, squeeze ratio, tightness rank, volume, distance to support, regime).
- Trees handle **different scales** (score 0–100 vs ratio 0.9) without `StandardScaler`.
- LightGBM is fast on small/medium tables and common in **tabular** finance research.

**Why not:**

- **Logistic regression:** simpler, more interpretable; weaker if relationships are nonlinear (squeeze *and* volume together).
- **sklearn `RandomForestClassifier`:** similar idea, often slower / slightly less accurate on this kind of data.
- **PyTorch LSTM on raw prices:** would need much more data, GPU, and a different leakage story. The project’s goal is “tune the *checklist*,” not invent a price-forecasting net.

**Important:** live `quant-launchpad` does **not** call the model. Docs call this Phase 1–2 research.

---

### 4. Walk-forward + embargo instead of random `train_test_split`

**Used in:** `walk_forward.py`, `training_set.py`.

**Why:** Stock examples are **not independent**. If NVDA is a hit on Saturday and you randomly put next Saturday in train and this Saturday in test, the model cheats.

Patterns:

- **Chronological split:** train on earlier dates, test on later.
- **Purge:** drop train rows whose gap to test is shorter than the label horizon (label path would overlap the test week).
- **Per-ticker embargo:** after keeping NVDA on day T, drop NVDA for the next 5 trading days so you don’t clone the same signal.

This is a standard **quant / time-series ML** pattern (also related to “purged k-fold” in López de Prado–style books).

---

### 5. Parquet cache + Postgres JSONB instead of “one giant CSV”

**Parquet:** columnar, compressed, typed. Good for “one file per ticker, thousands of rows.” CSV would be larger and slower; a database for every daily bar would be heavier than needed.

**Postgres JSONB (`ticker_results.detail`):** the scan payload is a **nested document** (eligibility checks, each factor’s `raw` fields). JSONB lets the dashboard and `extract_features()` read whatever was true *at scan time* without adding a SQL column every time a factor changes.

**psycopg + hand-written SQL** instead of SQLAlchemy: fewer moving parts for a homelab; you see the exact `INSERT ... ON CONFLICT` upsert. Cost: no ORM, no migration framework (called out in `docs/ARCHITECTURE_GAPS.md`).

**Yahoo / yfinance** instead of a paid vendor: free and good enough to learn; single point of failure (rate limits, missing Lynch rows).

---

# 5. How to run and experiment

## Set up and run (this machine)

The project is meant to run **in Docker**, not as a loose `python` on your laptop.

```bash
# 1. Go to the project
cd /opt/stacks/quant-hub

# 2. Secrets (Postgres password, DATABASE_URL, SMTP if you want email)
#    If .env already exists, skip this.
cp -n .env.example .env   # then edit POSTGRES_PASSWORD

# 3. Start database + app
docker compose up -d --build

# 4. Are both containers up?
docker compose ps

# 5. Create tables if needed, then sanity-check
docker exec quant-hub quant-hub init-db
docker exec quant-hub quant-hub status

# 6. See named universes (container reads /app/data = host /mnt/fast/quant-data/data)
docker exec quant-hub quant-universe list
docker exec quant-hub quant-universe show mega_runners
```

If you edited `data/universes/mega_runners.txt` in git, copy it to the live volume:

```bash
cp /opt/stacks/quant-hub/data/universes.json /mnt/fast/quant-data/data/universes.json
cp /opt/stacks/quant-hub/data/universes/mega_runners.txt /mnt/fast/quant-data/data/universes/mega_runners.txt
```

**Smallest Launchpad run (one ticker, cache on, write to DB):**

```bash
docker exec quant-hub quant-launchpad --tickers NVDA --cache --report json
docker exec quant-hub quant-hub status
```

Dashboard: `http://<this-host>:5002` (inside the container that is `quant-view`).

**Dry run (fake prices, no Yahoo — good for reading code):**

```bash
docker exec quant-hub quant-launchpad --tickers NVDA --dry-run --no-persist --report none
```

**Optional ML path** (needs historical Saturday scans first; see `docs/LAUNCHPAD_ML_GUIDE.md`):

```bash
docker exec quant-hub quant-ml warm-cache --universe mega_runners
docker exec quant-hub quant-backfill launchpad --universe mega_runners --since 2024-01-01
docker exec quant-hub quant-ml label --strategy launchpad --universe mega_runners --since 2024-01-01
docker exec quant-hub quant-ml export-features --strategy launchpad --universe mega_runners --since 2024-01-01 --horizon 20
docker exec quant-hub quant-ml train --strategy launchpad --universe mega_runners --since 2024-01-01 --horizon 20
```

**Tests (how the authors lock behavior):**

```bash
docker exec quant-hub pytest tests/unit/test_launchpad_rubric.py tests/unit/test_ml_labels.py -q
```

---

## Three small experiments (test your understanding)

Do these as **thought + tiny edits** (or ask Agent mode to apply them). After each, predict the result *before* you run.

### Exercise 1 — Eligibility is a gate, not the score

**Hypothesis:** If you raise the minimum price, more tickers become `filtered` even if squeeze looks great.

1. Open `src/quant_hub/scoring/launchpad.py` and find `price < 10.0` in `launchpad_eligibility_detail`.
2. Temporarily change `10.0` to `1000.0`.
3. Run:  
   `docker exec quant-hub quant-launchpad --tickers NVDA --cache --no-persist --report json`
4. Check the JSON report: `eligible` should be false, `filter_reason` like `price_below_10`, `tier` `filtered`. Factor scores can still be non-zero.

**Question to answer in your notes:** Where is the $10 rule applied — `aggregate.py` or `launchpad_eligibility_detail`? (Eligibility, before tiers.)

Revert the change when done.

---

### Exercise 2 — Cache hit vs Yahoo

**Hypothesis:** `--cache` skips Yahoo when `NVDA.parquet` is fresh.

1. Run once: `quant-launchpad --tickers NVDA --cache --no-persist --report none`
2. Find the file idea: `PRICE_CACHE_SUBDIR` in `config.py` → `data/cache/prices/1d/2y/NVDA.parquet` (on the host under `/mnt/fast/quant-data/data/...`).
3. Run again with `--cache`. Logs should mention cache hits (`ParquetCache.partition`).
4. Run with `--force-refresh` (CLI sets `use_cache=False`). That path treats everything as stale and calls `yf.download`.

**Question:** If you omit `--cache` entirely, does `partition` return all tickers as stale? (Yes — `if not use_cache: return [], tickers`.)

---

### Exercise 3 — What is a “label”?

**Hypothesis:** A label uses **future** closes, so a scan from yesterday cannot have a 63-day label yet.

1. Read `compute_forward_outcome` in `ml/labels.py`: `future = df[df["Date"] > anchor_date]` and `len(future) < horizon_days`.
2. After any recent Launchpad persist:  
   `docker exec quant-hub quant-ml label --strategy launchpad --universe mega_runners --since 2024-01-01`  
   (or whatever universe you actually scanned.)
3. `docker exec quant-hub quant-ml` status (or the `label` subcommand’s printed summary) — look for `insufficient_future_bars` vs `ok`.

**Question:** Why must entry be the **first close after** the anchor, not the scan day’s close? (Using the same-day close would mix “information you had at scan time” with “the label,” a form of leakage.)

**Bonus (no code):** In `ml/constants.py`, `LAUNCHPAD_FEATURE_COLUMNS` does **not** include MACD. Why might that be? (MACD is a Tier-1 *gate*, not part of the 100-pt raw score; the model is trained on the exported “setup shape” fields.)

---

## Suggested reading order (interactive path)

1. This guide, section 1 (you are here).
2. `cli/launchpad.py` → `application/scan_service.py` → `engine/runner.py` (one live scan).
3. `scoring/launchpad.py` + `indicators.py` (the math).
4. `infrastructure/cache/parquet_cache.py` + `yfinance_prices.py` (data).
5. `infrastructure/postgres/repository.py` `upsert_scan` (save).
6. `application/launchpad_backfill_service.py` `_backfill_one_date` (time travel).
7. `ml/labels.py` → `ml/features.py` → `ml/train.py` (ML).
8. `docs/LAUNCHPAD_SCANNER.md` and `docs/ML_FOUNDATION.md` when you want operator-level detail.

If you want a next session that stays in “teacher mode,” a good follow-up is: **open `indicators.py` and `score_squeeze_intensity` together** and walk every pandas line until the 40/25/0 point scale feels obvious.