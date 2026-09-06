# Learning Machine Learning with Quant Hub

**A hands-on training course built on this repository's real ML pipeline.**

**Who this is for:** Anyone learning ML by operating a real system — plus DevOps/Run Team members who need to keep it healthy.
**Prerequisites:** Comfort with a terminal, basic Python reading, no prior ML required.
**Time:** ~4 hours to work through all seven modules once.
**Verified against code:** 2026-09-05

---

## How to use this course

Each module follows the same shape, so you always know where you are:

1. **The concept** — the general ML idea, explained plainly.
2. **How this repo does it** — the actual files and constants, so the idea stops being abstract.
3. **Do it** — commands, with an explanation of *why* each flag exists before you run anything.
4. **Read the output** — how to tell success from silent failure.
5. **Checkpoint** — questions to confirm you understood before moving on.

Work the modules in order. Module 7 (operations) only makes sense once you understand what the pipeline produces.

### The one thing to understand before anything else

> **This system does not use machine learning to make its live decisions.**

Launchpad, the stock scanner users actually see, is a **rule-based** engine. It computes technical indicators, adds up points, and sorts. The ML pipeline runs **offline, after the fact**, to answer one question: *were those rules any good?*

This is a genuinely common and healthy pattern in industry, and it is the safest possible place to learn. You can train a bad model today and no user is affected. Keep this in mind — it explains almost every design decision you'll see, and it's the reason [Architecture Gaps](ARCHITECTURE_GAPS.md) lists live inference as an open item (P2) rather than a bug.

**Course map**

| Module | You will learn | Repo surface |
|---|---|---|
| 0 | ML vocabulary grounded in this codebase | — |
| 1 | Environment, dependencies, where things live | `pyproject.toml`, `docker/`, `config.py` |
| 2 | Data ingestion and why caching matters | `ml_cache_service.py`, `parquet_cache.py` |
| 3 | Features, and the leakage trap | `ml/features.py`, `scoring/launchpad.py` |
| 4 | Labels — turning the future into a target | `ml/labels.py` |
| 5 | Training a real gradient-boosted model | `ml/train.py`, `ml_train_service.py` |
| 6 | Evaluation, baselines, and walk-forward honesty | `ml/evaluate.py`, `ml/walk_forward.py` |
| 7 | MLOps: lifecycle, monitoring, troubleshooting, rollback | `docker/crontab`, `ml_models` |

---

# Module 0 — Vocabulary, using this project as the example

Read this once. You do not need to memorize it; later modules will use each term in context.

| Term | Plain meaning | In this project |
|---|---|---|
| **Sample / row** | One thing you learn from | One stock on one Saturday scan, e.g. `NVDA` on 2026-03-07 |
| **Feature** | A number describing the sample **at decision time** | Six numbers like `final_score`, `volatility_compression_ratio` |
| **Label / target** | The answer you want to predict | Did this stock rise ≥ 2% over the next N trading days? |
| **Horizon** | How far ahead the answer looks | 5, 10, 20, or 63 trading days |
| **Training set** | Rows the model learns from | Older scan dates |
| **Holdout / test set** | Rows kept hidden to grade the model | Newer scan dates |
| **Leakage** | Accidentally letting the model see the answer | Using tomorrow's price as a feature — fatal, covered in Module 3 |
| **Model / artifact** | The learned file | `model.txt` written by LightGBM |
| **Inference** | Using a trained model on new data | Only in evaluation here; **not** in production |
| **Baseline** | The simple thing you must beat | The existing rule-based `final_score` |
| **AUC** | Ranking quality, 0.5 = coin flip, 1.0 = perfect | Reported per model in `ml_models.metrics` |
| **Drift** | The world changes, model goes stale | **Not monitored here** — an honest gap |

**The single most important idea in the whole course:** a model is only interesting if it beats the boring alternative. This repo takes that seriously enough to compute the baseline automatically on every evaluation (Module 6).

---

# Module 1 — The environment you're learning in

## 1.1 The concept: ML needs reproducibility, not just code

An ML result is only trustworthy if someone else can rerun it. That means pinned-ish dependencies, a known data location, and a known configuration. Anything you can change by hand without leaving a trace is a future mystery.

## 1.2 How this repo does it

**Runtime.** Python **3.12**, running in one container built from `docker/Dockerfile`:

```dockerfile
FROM python:3.12-slim
RUN uv pip install --system -e .[dev,viz,ml]
```

That `[ml]` extra is what makes training possible:

```toml
ml = [
    "scikit-learn>=1.5.0",
    "lightgbm>=4.0.0",
]
```

**What you will and won't find.** There is **no** PyTorch, TensorFlow, ONNX, or MLflow. This is a **gradient-boosted trees** project, which is the right choice for small tabular data — and, in practice, still what most real-world tabular ML uses. LightGBM needs `libgomp1` (OpenMP) at the system level, which is why the Dockerfile installs it. Everything runs on **CPU**; there is no GPU anywhere in `docker-compose.yml`.

**Configuration.** No feature flags, no model config service. Just three layers:

- **Environment** — only `DATABASE_URL` really matters to ML. `config.database_url()` deliberately raises rather than defaulting to weak credentials.
- **Python constants** in `src/quant_hub/config.py`:

```python
ML_FEATURES_DIR = ML_DIR / "features"
ML_MODELS_DIR = ML_DIR / "models"
FEATURE_SCHEMA_VERSION = "v4"
DEFAULT_LABEL_HORIZONS = (5, 10, 20, 63)
LABEL_RETURN_THRESHOLD_PCT = 2.0
BENCHMARK_TICKER_FOR_LABELS = "SPY"
ML_LABEL_LOOKBACK_DAYS = 1260          # ~5 calendar years
ML_LABEL_CACHE_TTL_HOURS = 8760        # 1 year
```

- **CLI flags** on `quant-ml`, which override per run.

`FEATURE_SCHEMA_VERSION` is worth pausing on. It's stamped into every exported row and every registry entry. When you change what a feature *means*, you bump this string — otherwise, six months later, nobody can tell whether two models were trained on comparable data. This is versioning applied to data, and it is a habit worth stealing for your own projects.

**Where things live.** The container mounts a host volume, so the git checkout is *not* what runs:

| Container | Host |
|---|---|
| `/app/data/cache/prices/1d/5y/` | `/mnt/fast/quant-data/data/cache/prices/1d/5y/` |
| `/app/data/ml/features/` | `/mnt/fast/quant-data/data/ml/features/` |
| `/app/data/ml/models/` | `/mnt/fast/quant-data/data/ml/models/` |
| `/app/logs/ml.log` | `/mnt/fast/quant-data/logs/ml.log` |

**Prod** mounts `/mnt/fast/quant-data`. **Dev** uses Docker volumes plus bind-mounted repo universe files. Port 5002 + `/mnt/fast/quant-data` is not the practice stack. First-time install: [SETUP_GUIDE.md](SETUP_GUIDE.md). Do not `cp .env.example .env` or run bare `docker compose up`.

On **prod**, this trips up nearly everyone once: you edit a universe file in `/opt/stacks/quant-hub/data/`, the container never sees it, and you get `Unknown universe`. Copy to the volume, or use the **dev** bind-mount.

**The ML code itself** is small enough to read in an afternoon — that's intentional, and it's why this is a good place to learn:

```text
src/quant_hub/ml/
  constants.py      # schema version, feature names, label statuses
  labels.py         # forward-return math (Module 4)
  features.py       # JSONB → flat table (Module 3)
  training_set.py   # SQL join + filtering + embargo (Module 5)
  walk_forward.py   # chronological splits, purging (Module 6)
  train.py          # LightGBM fit / save / load (Module 5)
  evaluate.py       # AUC, top-K, baseline comparison (Module 6)
src/quant_hub/application/ml_*_service.py   # orchestration per CLI verb
src/quant_hub/cli/ml.py                     # the quant-ml command
```

## 1.3 Do it — confirm your environment before you learn anything else

Every command below runs inside the container. Run them one at a time and read the output.

**Step 1 — is the stack alive?**

```bash
./scripts/run_env.sh prod ps
# practice: ./scripts/run_env.sh dev ps
```

You want the app and Postgres containers up, with the database healthy. First-time Docker setup: [SETUP_GUIDE.md](SETUP_GUIDE.md). ML work touches Postgres constantly; if the DB is down, every later command fails with `Database unreachable` and you'll waste time debugging the wrong layer.

**Step 2 — can the ML tooling reach the database?**

```bash
docker exec quant-hub quant-ml status
```

`quant-ml status` counts rows in `signal_outcomes` grouped by label status. Right now, treat it purely as a connectivity check — the numbers will mean something after Module 4. Note it counts **globally**, across every strategy and universe, so it's a smoke test rather than a precise health metric.

**Step 3 — is LightGBM actually installed?**

```bash
docker exec quant-hub python -c "import lightgbm, sklearn; print(lightgbm.__version__, sklearn.__version__)"
```

Worth checking explicitly: LightGBM is imported *lazily*, inside `train_lightgbm_classifier`, not at module import. So a missing `[ml]` extra doesn't fail at startup — it fails minutes into a training run, after you've already waited.

## 1.4 Checkpoint

- Why does the training command fail late rather than immediately if LightGBM is missing?
- If you edit `data/universes/mega_runners.txt` in the git tree, will the container see it?
- What does `FEATURE_SCHEMA_VERSION` protect you from?

---

# Module 2 — Data ingestion: the unglamorous 80%

## 2.1 The concept: your model is a function of your data pipeline

Newcomers assume ML work is mostly modeling. It isn't. Most failures are data failures — missing rows, stale values, silently wrong timestamps. This module is about the plumbing, and the plumbing is where you'll spend most of your troubleshooting time in Module 7.

## 2.2 How this repo does it

**One source: Yahoo Finance**, via `yfinance`. That is a real single point of failure, and the project says so honestly in [Architecture Gaps](ARCHITECTURE_GAPS.md) (P1). When Yahoo is rate-limited or wrong, everything downstream degrades.

**Two separate caches**, and understanding why there are two is the point of this module:

| Cache | Window | TTL | Purpose |
|---|---|---|---|
| `prices/1d/2y` | ~2 years | **24 hours** | Live scanning — must be fresh |
| `prices/1d/5y` | ~1260 days | **8760 hours (1 year)** | ML labels — must be *deep* |

The live scanner needs **recent** data and refreshes daily. The ML pipeline needs **history**, both backwards (to replay old scans) and forwards (to see what happened after a scan). A one-year TTL on the ML cache would be reckless for live trading, but here it's deliberate: you refresh it explicitly with `warm-cache` rather than having it silently re-download five years of data during a label job.

**Quality guards exist at read time.** `ParquetCache.read` calls `drop_incomplete_ohlcv_bars`, so a partially-formed bar for today's still-open session doesn't get treated as a real close. Learn to appreciate this kind of guard — an incomplete final bar is exactly the sort of thing that produces a beautiful, completely fake backtest result.

**Fallback behavior.** The label service tries the 5y cache, then the 2y cache:

```python
def _read_prices(self, ticker: str):
    df = self._primary_cache.read(ticker)
    if (df is None or df.empty) and self._fallback_cache is not None:
        df = self._fallback_cache.read(ticker)
    return df
```

If both miss, the row is marked `no_price` rather than being silently dropped. Recording *why* a row is unusable, instead of just discarding it, is a small design choice with big payoff — Module 7 troubleshooting depends entirely on it.

## 2.3 Do it — warm the cache

```bash
docker exec quant-hub quant-ml warm-cache --universe mega_runners
```

**What this does, piece by piece:**

- `warm-cache` resolves the universe to a ticker list, then downloads ~1260 days of daily OHLCV for each one into the 5y Parquet cache.
- `--universe mega_runners` picks a small, intentional list (8 tickers) — the right size for learning. Defaulting to `sp500_index` here would mean hundreds of Yahoo requests before you understand what you're doing.
- **SPY is always added automatically**, whatever universe you name, because Module 4's labels compare every stock against the market. Skipping this quietly produces null excess returns.

If you need to force a refetch past the cache TTL:

```bash
docker exec quant-hub quant-ml warm-cache --universe mega_runners --force-refresh
```

Use `--force-refresh` sparingly. It bypasses the cache entirely and hits Yahoo for every ticker, which is exactly how you get rate-limited.

## 2.4 Read the output

You'll get a line like `tickers=9 rows=11340`. Two quick sanity checks:

- **Ticker count** should be your universe **plus one** (SPY). If it isn't, the universe didn't resolve the way you expected.
- **Rows** should be roughly `tickers × ~1250`. Dramatically fewer means Yahoo returned short history — common for recently-listed tickers, and a legitimate reason some rows can never be labeled.

Verify on disk:

```bash
docker exec quant-hub ls -la /app/data/cache/prices/1d/5y/ | head -20
```

## 2.5 Checkpoint

- Why does the ML cache have a one-year TTL while the scan cache expires daily?
- What happens to a label if the price cache is empty for that ticker — error, skip, or recorded status?
- Why is SPY downloaded even when it isn't in your universe?

---

# Module 3 — Features, and the leakage trap

## 3.1 The concept: a feature must be knowable at decision time

This is the most important module in the course.

A feature is any number you give the model as input. The rule that governs all of them: **you may only use information that existed at the moment of the decision.** Violate this and you get *leakage* — the model appears brilliant in testing and is worthless in production, because in production the future isn't available.

Leakage is the single most common way ML projects fail, and it is sneaky. It rarely looks like "I used tomorrow's price." It looks like a column that was quietly recomputed later, or a training row whose timestamp is subtly wrong.

## 3.2 How this repo does it

**Features come from a rule-based scan that already ran.** The Launchpad engine (`engine/runner.py`) evaluates each stock and stores its full reasoning as JSONB in `ticker_results.detail`. The ML pipeline reads **only that stored payload**. It never recomputes indicators, which means it structurally cannot see later data. That's leakage prevention by architecture rather than by discipline, and it's much more reliable.

**The scan itself works like this** (worth understanding, because these are your features' parents):

1. **Eligibility filters** — enough history, price ≥ $10, sufficient volume, above the 200-day EMA, near EMA50 or a support shelf. Failures get `tier = filtered`.
2. **Five factors**, each capped at a point value:

| Factor | Max points | Measures |
|---|---|---|
| `squeeze_intensity` | 40 | Volatility compression (ATR short vs long) |
| `volume_vacuum_depth` | 30 | Volume drying up vs baseline |
| `tightness_percentile` | 15 | How tight the range is historically |
| `trend_proximity_match` | 15 | Relative strength + distance to support |
| `macd_zero_line` | 25 | **Tier-1 gate only — not in the 100-pt score** |

3. **Aggregate** to a 0–100 normalized score, then assign tiers: Tier 1 (≥80 **and** MACD ≥ 25), Tier 2 (≥65), Tier 3, or filtered.

**The six ML features** (`LAUNCHPAD_FEATURE_COLUMNS`) are a deliberately small subset:

| Feature | Read from | Intuition |
|---|---|---|
| `final_score` | `summary.final_adjusted_score` | What the rules concluded |
| `volatility_compression_ratio` | `scores.squeeze_intensity.raw.squeeze_ratio` | Is the spring coiled? |
| `relative_strength_rank` | `scores.tightness_percentile.raw.tightness_rank_pct` | Tight relative to its own history? |
| `volume_rs_score` | `scores.volume_vacuum_depth.raw.rvol` | Has supply dried up? |
| `resistance_distance_pct` | `scores.trend_proximity_match.raw.pct_distance` | Distance to EMA50/support |
| `market_regime_multiplier` | `scan_runs.regime_multiplier` | Was the overall market strong? |

Notice the design: features are the **raw underlying measurements**, not the points the rules assigned. This lets the model disagree with the scoring rules — which is the entire reason to train a model here. If you fed it only the final points, it could at best re-derive the rules it was meant to critique.

One nuance about `market_regime_multiplier`. The regime (`strong` 1.0 / `neutral` 0.85 / `weak` 0.6) is computed from SPY and stored on the scan run. But in `strategies/launchpad/aggregate.py`, the per-ticker multiplier is currently hardcoded to `1.0`, so `final_score` equals `normalized_score`. The **run-level** regime still flows into the feature. Small discrepancies like this between what a name suggests and what the code does are exactly what you should learn to check rather than assume.

**Leakage is enforced by a test**, which is a practice worth copying:

```python
def test_launchpad_feature_columns_exclude_leakage():
    forbidden = {
        "forward_return_pct",
        "forward_max_gain_pct",
        "label_binary",
        "label_status",
        ...
    }
    assert forbidden.isdisjoint(set(LAUNCHPAD_FEATURE_COLUMNS))
```

A unit test that fails when someone adds an outcome column to the feature list is worth more than a paragraph in a wiki.

## 3.3 Do it — export features and look at them

You need historical scans first. If they don't exist yet, create point-in-time ones:

```bash
docker exec quant-hub quant-backfill coverage --strategy launchpad --universe mega_runners --since 2024-01-01
```

`coverage` is a **preview**. It plans Saturday scan dates, compares them to what's already in Postgres, and prints planned/existing/missing counts plus the earliest date your cache can support. Always run it before a real backfill — it costs seconds and prevents a long job that turns out to be misaimed.

```bash
docker exec quant-hub quant-backfill launchpad --universe mega_runners --since 2024-01-01
```

This replays historical Saturdays. The critical mechanic: for each date, daily prices are **truncated to that date** (`truncate_daily_to_date`) before scoring, so a 2024 scan cannot see 2025 prices. That's how the project manufactures honest training history. Useful flags: `--dry-run` (score without writing), `--no-resume` (recompute dates already stored), `--until` (stop early).

Now export:

```bash
docker exec quant-hub quant-ml export-features \
  --strategy launchpad \
  --universe mega_runners \
  --since 2024-01-01 \
  --horizon 20
```

- `export-features` flattens each stored JSONB payload into one tabular row and writes Parquet.
- `--horizon 20` joins the 20-trading-day label to each row. **If you omit it, the default is 10** — and quietly analyzing a different horizon than you intended is a classic self-inflicted wound.
- `--no-labels` exports features alone; `--per-run` writes one file per scan instead of one combined file.

Files land at `/app/data/ml/features/launchpad/mega_runners/features_*_h20.parquet`.

## 3.4 Read the output

Inspect the actual data — do this every time you change anything:

```bash
docker exec quant-hub python -c "
import pandas as pd, glob
f = sorted(glob.glob('/app/data/ml/features/launchpad/mega_runners/*_h20.parquet'))[-1]
df = pd.read_parquet(f)
print(df.shape)
print(df[['scan_date','ticker','tier','final_score','label_status','forward_return_pct']].head(10))
print(df['label_status'].value_counts())
"
```

What to look for: are the tier values plausible, are features populated rather than all-null, and how many rows are actually usable? The export deliberately includes **every** row, including `filtered` ones and unlabeled ones — filtering happens later, at training time (Module 5). Exporting everything means you can diagnose *why* rows were dropped instead of guessing.

## 3.5 Checkpoint

- Why does the ML code read stored JSONB instead of recomputing indicators from prices?
- Why are raw measurements better features here than the points the rules assigned?
- `macd_zero_line` is a Tier-1 gate but isn't in the 100-point score, and isn't an ML feature. Should it be? (There's no single right answer — but you should be able to argue both sides.)

---

# Module 4 — Labels: turning the future into a target

## 4.1 The concept: supervised learning needs an answer key

To learn "which setups work," you need to define **worked** as a number. That definition is a modeling decision, not a technical detail, and reasonable people disagree about it. Making it explicit — and writing it down — is the job.

## 4.2 How this repo does it

The definition, in `ml/labels.py`, is five steps:

1. **Anchor** on the scan's `as_of_price` date from provenance, falling back to `scan_date`.
2. **Enter** at the first close **strictly after** the anchor.
3. **Exit** after `horizon_days` trading rows.
4. **Measure** total return, max gain, and max drawdown along that path.
5. **Compare** to SPY over the same window for excess return.

Step 2 is the one that matters most. `df[df["Date"] > anchor_date]` — strictly greater. If you entered at the *same day's* close, you'd be assuming you could trade on a price that was only known after the scan decision. That single character is the difference between an honest label and a fantasy.

**The binary target** is simple: `forward_return_pct >= 2.0`. Note what it is *not* — it is not excess return versus SPY. Excess is computed and stored, but the training target is raw return. That's a legitimate simplification with a real consequence: in a strong bull market, almost everything clears +2%, so the classes become imbalanced and AUC gets less meaningful. Being able to spot that kind of interaction between label design and metric reliability is a genuinely valuable skill.

**Four horizons are labeled at once** (5, 10, 20, 63), so you can ask the same question at different time scales without recomputing.

**Status codes instead of silent drops** — this is the part to internalize:

| `label_status` | Meaning | Usable? |
|---|---|---|
| `ok` | Full horizon computed | **Yes** |
| `no_price` | Ticker absent from both caches | No — fix with `warm-cache` |
| `invalid_anchor` | No bars at all after the anchor | No — usually a bad date |
| `insufficient_future_bars` | Fewer than `horizon_days` sessions available | No — **normal for recent scans** |
| `pending` | Schema default | No — shouldn't persist after a job |

`insufficient_future_bars` is not an error. A scan from last week simply cannot have a 63-day outcome yet. And because labels are **upserted** on `(run_id, ticker, horizon_days)`, rerunning the job later flips those rows to `ok` as time passes. That's why the scheduled weekly job is a *labeling* job — it's harvesting answers that have finally become available.

## 4.3 Do it — compute labels

```bash
docker exec quant-hub quant-ml label \
  --strategy launchpad \
  --universe mega_runners \
  --since 2024-01-01
```

- `label` walks matching scan runs, reads each ticker's cached prices, and computes outcomes for all four horizons.
- `--since` bounds the work. Without it you re-label all history, which is slow and usually unnecessary.
- `--horizons 5,10,20,63` overrides the default set; `--threshold 2.0` overrides the binary cutoff. Changing the threshold **redefines your target**, so any model trained before and after is no longer comparable — treat it as a versioned decision, not a tweak.
- `--run-id N` labels exactly one run, which is the fastest way to debug a single suspicious scan.

## 4.4 Read the output

The summary looks like:

```text
runs=52 tickers=416 outcomes=1664 status[insufficient_future_bars=120, ok=1544]
```

How to read it:

- `outcomes` ≈ `tickers × 4 horizons`. Materially less means tickers were skipped.
- A modest `insufficient_future_bars` count concentrated in **recent** dates is healthy.
- `no_price` anywhere means go back to Module 2 and warm the cache.
- `insufficient_future_bars` on **old** dates is a real red flag — it suggests truncated cache data, not the passage of time.

Check the distribution properly with SQL:

```sql
SELECT sr.universe_id, so.horizon_days, so.label_status, COUNT(*)
FROM signal_outcomes so
JOIN scan_runs sr ON sr.id = so.run_id
WHERE sr.strategy_id = 'launchpad'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
```

And look at class balance, since it determines whether your metrics will mean anything:

```sql
SELECT label_binary, COUNT(*)
FROM signal_outcomes
WHERE horizon_days = 20 AND label_status = 'ok'
GROUP BY label_binary;
```

Wildly uneven classes (say 90/10) mean accuracy is useless and even AUC needs cautious interpretation.

## 4.5 Checkpoint

- Why does entry use the first close *strictly after* the anchor?
- A scan from three days ago shows `insufficient_future_bars` at h63. Bug or expected?
- You change `--threshold` from 2.0 to 5.0. Can you compare the resulting model to yesterday's? Why not?

---

# Module 5 — Training your first model

## 5.1 The concept: fitting, and the discipline around it

The actual fitting is anticlimactic — a few lines calling LightGBM. Everything valuable happens in the preparation: which rows qualify, how you split them, and what you record afterward.

**Gradient-boosted decision trees**, in one paragraph: build a small tree that predicts the target badly, then build another tree that predicts the *first tree's mistakes*, and repeat. Each tree is weak; the ensemble is strong. It handles mixed-scale numeric features without normalization and works well on small tabular datasets — which is exactly this situation.

## 5.2 How this repo does it

**Row selection** (`ml/training_set.py`) applies five filters in order, and each one teaches something:

1. **Setups only** (default) — keep Tier 1/2/3, drop `filtered`. You're modeling *setups that qualified*, not the whole market. `--all-tiers` includes everything and usually worsens class balance.
2. **`label_status == 'ok'`** — never train on rows whose outcome couldn't be computed.
3. **Drop null targets.**
4. **Per-ticker embargo** — after keeping a row for a ticker on date T, drop that ticker's rows for the next **5 business days**.
5. **Drop rows with any missing feature.**

Filter 4 deserves attention, because it's the kind of thing that separates a careful practitioner from a careless one. If NVDA appears in four consecutive weekly scans, those four rows have heavily overlapping forward windows — they're nearly the same observation counted four times. The model sees inflated confidence, and your metrics lie to you. The embargo enforces independence:

```python
keep_idx.append(idx)
embargo_end_by_ticker[ticker] = scan_ts + pd.tseries.offsets.BDay(embargo_trading_days)
```

On a small universe this can remove a lot of rows. That's the correct tradeoff — fewer honest samples beat many correlated ones.

**Chronological splitting.** With ≥26 distinct scan dates, the default split is the 26th-from-last date: train on everything before, test on everything after. **Never random-shuffle time-series data.** A random split lets the model train on March and April and get tested on the March it already saw — a leak that will not show up as an error, only as an unrealistically good score.

**The hyperparameters** (`ml/train.py`):

```python
DEFAULT_LGBM_PARAMS = {
    "objective": "binary",
    "metric": "auc",
    "num_leaves": 15,
    "learning_rate": 0.05,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "min_child_samples": 5,
    "seed": 42,
}
# num_boost_round defaults to 100
```

These are deliberately conservative for a small dataset: shallow trees (`num_leaves=15`), a slow learning rate, and per-iteration sampling of rows and columns. All three fight **overfitting** — memorizing your specific rows instead of learning a general pattern. `seed=42` makes runs reproducible, which matters more than it sounds: without it, you can't tell whether a metric changed because of your improvement or because of randomness.

There's no hyperparameter config file and no tuning search. For learning purposes that's a feature, not a gap — you should understand the defaults before you start searching.

**What gets recorded.** Every train writes three things:

- `model.txt` — the LightGBM model
- `features.json` — feature columns plus strategy/universe/horizon
- a row in `ml_models` — parameters, metrics, training window, split date, schema version

That registry row is the "what exactly did I run?" record. Without it, models in a folder become anonymous within weeks.

## 5.3 Do it — train

```bash
docker exec quant-hub quant-ml train \
  --strategy launchpad \
  --universe mega_runners \
  --since 2024-01-01 \
  --horizon 20 \
  --name lesson1_mega_h20
```

Flag by flag:

- `--horizon 20` must match the horizon you labeled and care about. **The default is 10** — this mismatch is the most common beginner error in this pipeline.
- `--since` bounds training history.
- `--name` sets the registry name. **Always pass it.** The auto-generated name is `{strategy}_{universe}_h{horizon}_{YYYYMMDD}`, and `ml_models.name` has a **UNIQUE** constraint — so a second train on the same day with defaults fails at insert.
- `--split-date` overrides the automatic holdout boundary.
- `--all-tiers` disables setups-only filtering.
- `--top-k 5` sets how many top-ranked names per scan date the return metric uses.

## 5.4 Read the output

```text
model_id=3 name=lesson1_mega_h20 train_rows=142 holdout[n=38 weeks=26 auc=0.5412 ml_top5_ret=1.83% score_top5_ret=1.42%]
top features: volatility_compression_ratio=284, final_score=201, ...
```

Read it in this order:

1. **`train_rows`** — with only ~142 rows, nothing that follows is statistically meaningful. That is the expected result on `mega_runners` and it is *fine*; you are validating plumbing, not discovering alpha.
2. **`auc`** — 0.54 is barely above the 0.50 coin flip. On this sample size, don't over-interpret in either direction.
3. **`ml_top5_ret` vs `score_top5_ret`** — the model's picks versus the existing rules' picks. This comparison is the actual product question.
4. **feature importance** — by *gain*, meaning how much each feature improved predictions when used for a split. Useful for intuition, but do not read causality into it.

To see why rows disappeared, check the drop counters in the log:

```bash
docker exec quant-hub grep "Training set built" /app/logs/ml.log | tail -5
```

```text
raw=980 tier_ok=420 label_ok=390 final=142 drops[tier=560 label=30 target=0 features=8 embargo=240]
```

This line is the best diagnostic in the whole system. Here, 560 rows were filtered tiers and 240 were embargoed — both **by design**. If `final` is 0, this line tells you precisely which filter ate everything.

## 5.5 Checkpoint

- Why must the split be chronological rather than random?
- What problem does the 5-day per-ticker embargo solve, and what does it cost?
- You train twice with no `--name` on the same day. What happens, and why?
- Your training set has 142 rows. What conclusions are you entitled to draw?

---

# Module 6 — Evaluation: learning not to fool yourself

## 6.1 The concept: the baseline decides whether you have anything

An AUC of 0.58 sounds like a result. It is meaningless in isolation. The real question is always **compared to what?** — and the honest comparison is the simplest thing that already works.

This project gets that right structurally: `evaluate.py` computes the rule-based baseline automatically on every evaluation, so you cannot report a model score without also seeing what the existing rules achieved.

## 6.2 How this repo does it

**Four metrics**, and one of them has a misleading name you should know about:

- **AUC** — probability the model ranks a random winner above a random loser. Returns `None` if only one class is present, rather than crashing or reporting a fake number.
- **`precision_at_k` / `recall_at_k`** — despite the names, these are **plain precision and recall at a 0.5 probability threshold**, not ranking-at-K metrics:

```python
y_pred = (y_score >= 0.5).astype(int)
metrics.precision_at_k = float(precision_score(y_true, y_pred, zero_division=0))
```

Read the code, not the field name. This is a good habit generally, and a concrete example of why.

- **`mean_forward_return_top_k`** — group rows by `scan_date`, take the model's top 5, average their forward returns, then average across dates. This mirrors how someone would actually use the system: pick a handful of names each week.
- **`baseline_score_top_k_return`** — the identical calculation using `final_score`. The difference between the two is reported as `return_lift_vs_baseline`.

**Walk-forward validation** is the honest way to evaluate a time-series model. One holdout tells you about one period, which might have been a lucky quarter. Walk-forward slides through history: train on 52 weeks, test on the next 13, advance, repeat.

Two subtleties matter:

**Purging.** A row labeled with a 20-day horizon has an outcome extending 20 days past its scan date. If that window overlaps the test period, the model is being trained on knowledge of the test window. `purge_train_dates` drops those rows, converting trading days to calendar days with `ceil(max(horizon, 5) × 7 / 5)`. This is subtle, easy to omit, and the reason many published backtests are wrong.

**Walk-forward retrains per fold.** This one surprises people:

```python
fold_booster = train_lightgbm_classifier(X.loc[train_mask], y.loc[train_mask], params=train_params)
```

It does **not** score your saved `model.txt`. Each fold trains a fresh model. So walk-forward is evaluating your **process** — "does this feature set and configuration produce useful models repeatedly?" — rather than grading one artifact. Both questions are valid; know which one you asked.

## 6.3 Do it — evaluate two ways

**The saved artifact:**

```bash
docker exec quant-hub quant-ml evaluate --model-id 3
```

This loads `model.txt` and `features.json`, rebuilds the same dataset, and scores rows on or after the recorded `eval_split_date`. Results merge into `ml_models.metrics.evaluation`, so the registry accumulates history rather than overwriting it.

**The process:**

```bash
docker exec quant-hub quant-ml evaluate \
  --model-id 3 \
  --walk-forward \
  --train-weeks 52 \
  --test-weeks 13 \
  --json
```

- `--walk-forward` switches to rolling folds with purging.
- `--train-weeks 52` / `--test-weeks 13` size each window; the step equals `test_weeks`, so test windows don't overlap.
- `--json` prints the full metrics dictionary.
- `--artifact-path DIR` evaluates a model directory directly, without a registry id.

**Important:** if your history has fewer than `train_weeks + test_weeks` distinct scan dates, you get **zero folds and empty metrics** — not an error. On two years of Saturdays (~104 dates) with 52+13, you'll get roughly four folds. Shrink the windows on smaller datasets.

## 6.4 Read the output

```text
model_id=3 folds=4 mean_auc=0.5610 mean_return_lift=0.31
  split=2025-01-04 train=88 purged_from=52 auc=0.5900 ml_top5_ret=2.10% score_top5_ret=1.60%
  split=2025-04-05 train=95 purged_from=52 auc=0.5100 ml_top5_ret=1.20% score_top5_ret=1.90%
  ...
```

Interpretation, in order of importance:

- **Consistency beats average.** Folds at 0.59, 0.51, 0.62, 0.49 average out to something respectable while telling you the model is unstable. Look at the spread, not just `mean_auc`.
- **`mean_return_lift`** is the headline. Positive and consistent means the model adds something over the rules. Negative means the rules are winning — a perfectly good finding, and one you should report rather than bury.
- **`purged_from`** shows how many train dates were considered before purging. A large gap between that and `train` is purging doing its job.

Honest expectations on `mega_runners`: 8 tickers over a couple of years is a few hundred rows before filtering, and maybe a hundred after. Metrics will bounce around. **This is the correct outcome for a learning exercise.** The pipeline is what you're validating.

## 6.5 Checkpoint

- Why is AUC alone insufficient to justify a model here?
- Walk-forward reports good numbers. Does that mean your saved `model.txt` is good?
- What does purging prevent, and why doesn't a plain chronological split handle it?
- A fold reports `auc=None`. What happened?

---

# Module 7 — MLOps: keeping it alive

## 7.1 The concept: models are systems, not files

Training is a one-day activity. Operating is forever. MLOps is everything that keeps a model trustworthy over time: scheduling, monitoring, diagnosing, and reverting.

This project is deliberately modest here, and studying an honest, partial implementation teaches more than reading about an idealized one.

## 7.2 Lifecycle — what's automated and what isn't

**Automated: labeling only.** From `docker/crontab` (the authoritative source — always verify the installed copy rather than trusting docs, including this one):

| When (ET) | Job |
|---|---|
| Mon–Fri 17:10–17:25 | `quant-launchpad-daily` for `most_actives`, `large_cap_growth`, `small_cap_growth`, `mid_cap_growth` |
| Sat 07:00–07:36 | `quant-ml label --strategy launchpad --universe <each> --since $(date -d '90 days ago' +%Y-%m-%d)` |

```bash
docker exec quant-hub cat /etc/cron.d/quant-hub
```

The weekday scans create signals; Saturday labeling harvests outcomes that have matured. The rolling 90-day window is well-chosen: long enough for 63-day horizons to complete, short enough to stay cheap.

**Not automated:** `warm-cache`, `export-features`, `train`, `evaluate`, and backfill. Retraining is a human decision here. Given that no user-facing behavior depends on the model, that's a reasonable choice — automating retraining before automating monitoring would be building the wrong thing first.

**Promotion.** There's no staging environment, no approval workflow, and no "production model" pointer. `ml_models.status` accepts `active` or `archived`, but **no CLI sets it** — you write SQL. Knowing where the automation ends is as important as knowing what it does.

The full manual cycle, which is Modules 2–6 in sequence:

```bash
docker exec quant-hub quant-backfill coverage --strategy launchpad --universe mega_runners --since 2024-01-01
docker exec quant-hub quant-backfill launchpad --universe mega_runners --since 2024-01-01
docker exec quant-hub quant-ml warm-cache --universe mega_runners
docker exec quant-hub quant-ml label --strategy launchpad --universe mega_runners --since 2024-01-01
docker exec quant-hub quant-ml export-features --strategy launchpad --universe mega_runners --since 2024-01-01 --horizon 20
docker exec quant-hub quant-ml train --strategy launchpad --universe mega_runners --since 2024-01-01 --horizon 20 --name run_$(date +%Y%m%d)
docker exec quant-hub quant-ml evaluate --model-id <id> --walk-forward
```

## 7.3 Monitoring — what exists, and what honestly doesn't

**What you have:**

| Source | Shows |
|---|---|
| `/mnt/fast/quant-data/logs/ml.log` | Every `quant-ml` run |
| `/mnt/fast/quant-data/logs/cron.log` | Scheduled jobs |
| `/mnt/fast/quant-data/logs/backfill.log` | Historical scans |
| `quant-ml status` | Global label-status counts |
| `quant-ml models` | Registry with holdout AUC |
| SQL on `signal_outcomes` / `ml_models` | Everything, precisely |

```bash
docker exec quant-hub quant-ml models --strategy launchpad --limit 20
```

```sql
SELECT id, name, universe_id, horizon_days, status, created_at,
       metrics->'holdout'->>'auc'        AS holdout_auc,
       metrics->'evaluation'->>'mean_auc' AS walkforward_auc
FROM ml_models
ORDER BY created_at DESC
LIMIT 20;
```

**What you don't have** — and you should be able to name these, because interviewers and auditors ask:

- **Data drift detection.** Nothing compares today's feature distributions to training. If volatility regimes shift, nothing warns you.
- **Concept drift detection.** No rolling production AUC — because there's no production inference to measure.
- **Alerting.** Failures are log-only ([Architecture Gaps](ARCHITECTURE_GAPS.md), H1). A silently failing Saturday job goes unnoticed until someone reads the log.
- **Structured metrics.** No Prometheus, no OpenTelemetry.
- **Model staleness tracking.**

The mitigating factor is real: with no live inference, drift can't hurt users. It only makes your *research* stale. Understanding *why* a gap is acceptable in one architecture and unacceptable in another is more valuable than reciting a best-practices list.

**A practical weekly check** (two minutes):

```bash
docker exec quant-hub grep "quant-ml label" /app/logs/cron.log | tail -8
docker exec quant-hub quant-ml status
```

You're confirming the four Saturday jobs ran and that `no_price` isn't climbing.

## 7.4 Troubleshooting — think in layers

When something breaks, work bottom-up: **database → cache → scans → labels → training**. Most "the model is broken" reports are actually cache or scan problems two layers down.

| Symptom | First check | Fix |
|---|---|---|
| `Database unreachable` | `./scripts/run_env.sh prod ps` | Fix `DATABASE_URL` in `.env.prod`; recreate |
| `Unknown universe 'X'` | Files on the **volume**, not git | Copy to `/mnt/fast/quant-data/data/` |
| Labels all `insufficient_future_bars` | Are dates recent? | Normal if so; else warm cache |
| Many `no_price` | `ls` the 5y cache | `warm-cache --force-refresh`, relabel |
| Empty training set | `grep "Training set built"` in `ml.log` | Read the drop counters |
| Train exits 1, `model_id=None` | Same log line | Usually no `ok` labels or all tiers filtered |
| Walk-forward returns nothing | Count distinct scan dates | Lower `--train-weeks`/`--test-weeks` |
| Unique violation on `ml_models.name` | Trained twice today, no `--name` | Pass `--name` |
| Code change has no effect | Image is stale | `./scripts/run_env.sh prod up --build -d` |
| Dashboard shows no ML | — | **Expected.** No live inference. |

**Fallback behavior, stated plainly:** when the ML pipeline is broken, the product keeps working, because Launchpad is rule-based. There is no ML circuit breaker because there is nothing to break. If Yahoo is down, scans degrade to `no_price_data` and labels to `no_price` — and you should **not** delete `scan_runs` to force a retry. Those runs are your training history, and deletion cascades to labels.

## 7.5 Rollback — how to revert without a serving layer

Since nothing serves models, "rollback" means restoring the research baseline and the files that back it.

**Step 1 — find the model you want:**

```bash
docker exec quant-hub quant-ml models --strategy launchpad --universe mega_runners
```

**Step 2 — confirm the artifact exists:**

```bash
docker exec quant-hub ls -la /app/data/ml/models/<older_name>/
```

You need both `model.txt` and `features.json`. Without the sidecar, `load_model_artifact` can't know the column order, and column order matters.

**Step 3 — verify it still evaluates:**

```bash
docker exec quant-hub quant-ml evaluate --artifact-path /app/data/ml/models/<older_name>
```

Never mark a model as the baseline without confirming it loads and scores.

**Step 4 — update status (SQL, since no CLI does this):**

```sql
UPDATE ml_models SET status = 'archived' WHERE id = <new_bad_id>;
UPDATE ml_models SET status = 'active'   WHERE id = <old_good_id>;
```

**Step 5 — if files were overwritten**, restore from backup of `/mnt/fast/quant-data/data/ml/models/`. There is no artifact versioning beyond unique names — which is exactly why Module 5 insists on `--name`.

**Note:** rolling back *scanner rules* is different. Those are code, so it's a git revert plus rebuild. Historical `ticker_results` keep whatever the engine produced at the time, which is correct — you don't want history rewritten under you.

## 7.6 Maintenance calendar

| Cadence | Task |
|---|---|
| Weekly | Confirm Saturday label jobs ran; scan `ml.log` for errors |
| After universe changes | `warm-cache` that universe; relabel affected dates |
| After scoring-code changes | Rebuild; backfill `--no-resume` for affected dates; relabel; retrain with a new `--name` |
| Before large backfills | `pg_dump` first; check disk on `/mnt/fast` |
| Quarterly | Retrain on the largest universe you have; compare walk-forward to the previous model |

```bash
# Prod names and path. Dev: quant-hub-db-dev / quant_hub_dev (no /mnt/fast/quant-data).
docker exec quant-hub-db pg_dump -U quant quant_hub \
  -t scan_runs -t ticker_results -t signal_outcomes -t ml_models \
  > /mnt/fast/quant-data/backups/ml_$(date +%F).sql
```

Restore drills are **not** automated ([Architecture Gaps](ARCHITECTURE_GAPS.md), H2). An untested backup is a hypothesis.

## 7.7 Checkpoint

- What is automated weekly, and what still requires a human?
- Why is the absence of drift monitoring defensible in *this* architecture but not in a system serving live predictions?
- Walk through rollback when the artifact directory was overwritten.
- Why must you never truncate `scan_runs` to "clean up"?

---

# The rules that don't bend

Six guardrails. Every one of them exists because violating it produces results that look good and are wrong.

1. **Never shuffle time-series data randomly.** Chronological splits only.
2. **Never train on rows where `label_status != 'ok'`.**
3. **Never let future information into a feature.** Export from stored payloads; don't recompute.
4. **Never truncate `scan_runs`.** Labels cascade-delete with it.
5. **Never treat small-universe metrics as evidence.** `mega_runners` validates plumbing, not edge.
6. **Never wire live inference without walk-forward evidence and an explicit decision.** ([Architecture Gaps](ARCHITECTURE_GAPS.md), P2.)

---

# Where to go next

**Exercises, roughly in order of difficulty:**

1. Train at h5, h10, h20, and h63 on the same data. Which horizon separates winners best, and can you explain why?
2. Run with `--all-tiers` and compare. What happened to class balance and to AUC?
3. Set the embargo to 0 in a scratch copy of `walk_forward.py`. Watch metrics improve — then explain precisely why that improvement is fake.
4. Add a seventh feature from the JSONB payload. Bump `FEATURE_SCHEMA_VERSION`. Does it help?
5. Scale to `large_cap_growth` and repeat the whole cycle. Do the small-universe conclusions survive?

**Reading the source, in the order that makes sense:**

`ml/labels.py` (smallest, most important) → `ml/features.py` → `ml/training_set.py` → `ml/walk_forward.py` → `ml/evaluate.py` → `ml/train.py`.

**Companion docs:** [ML Foundation](ML_FOUNDATION.md) for design principles · [Launchpad ML Guide](LAUNCHPAD_ML_GUIDE.md) for the tuning loop · [Data Model](DATA_MODEL.md) for schema · [Runbook](RUNBOOK.md) for general ops · [Architecture Gaps](ARCHITECTURE_GAPS.md) for known limitations.

---

## Appendix A — Command reference

Reach for this **after** the modules, not instead of them.

```bash
# Ingestion (Module 2)
quant-ml warm-cache [--universe ID] [--force-refresh]

# Historical scans (Module 3)
quant-backfill coverage --strategy launchpad --universe ID --since DATE
quant-backfill launchpad --universe ID --since DATE [--until DATE] [--no-resume] [--dry-run]

# Features (Module 3)
quant-ml export-features [--strategy S] [--universe U] [--since D] [--until D]
                         [--horizon N] [--no-labels] [--per-run] [--run-id N]

# Labels (Module 4)
quant-ml label [--strategy S] [--universe U] [--since D] [--until D]
               [--horizons 5,10,20,63] [--threshold 2.0] [--run-id N]

# Training (Module 5)
quant-ml train --since D [--until D] [--universe U] [--horizon 10]
               [--split-date D] [--name NAME] [--all-tiers] [--top-k 5]

# Evaluation (Module 6)
quant-ml evaluate (--model-id N | --artifact-path DIR)
                  [--walk-forward] [--train-weeks 52] [--test-weeks 13] [--json]

# Inspection (Module 7)
quant-ml status
quant-ml models [--strategy S] [--universe U] [--status active|archived] [--limit 20]
```

**Exit code 1** means: database unreachable, zero runs labeled (without `--run-id`), zero rows exported, no `model_id` produced, or evaluation metrics containing `error`. Worth wiring into any script you write.

## Appendix B — Schema

```sql
CREATE TABLE IF NOT EXISTS signal_outcomes (
    run_id BIGINT NOT NULL REFERENCES scan_runs(id) ON DELETE CASCADE,
    ticker VARCHAR(16) NOT NULL,
    horizon_days INT NOT NULL,
    anchor_date DATE NOT NULL,
    forward_return_pct DOUBLE PRECISION,
    forward_max_gain_pct DOUBLE PRECISION,
    forward_max_drawdown_pct DOUBLE PRECISION,
    spy_forward_return_pct DOUBLE PRECISION,
    excess_return_pct DOUBLE PRECISION,
    label_binary BOOLEAN,
    label_status VARCHAR(32) NOT NULL DEFAULT 'pending',
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, ticker, horizon_days)
);

CREATE TABLE IF NOT EXISTS ml_models (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL UNIQUE,     -- collides if you skip --name
    strategy_id VARCHAR(32) NOT NULL,
    universe_id VARCHAR(64) NOT NULL,
    horizon_days INT NOT NULL,
    feature_schema_version VARCHAR(16) NOT NULL,
    model_type VARCHAR(64) NOT NULL,       -- lightgbm_classifier
    train_params JSONB,
    metrics JSONB,
    feature_columns JSONB,
    artifact_path TEXT NOT NULL,
    train_since DATE,
    train_until DATE,
    eval_split_date DATE,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

The `ON DELETE CASCADE` on `signal_outcomes.run_id` is guardrail #4 expressed in SQL: delete a scan run and its labels vanish with it.

## Appendix C — Documentation drift warning

Older docs in this repo state that Saturday labeling covers `sp500_index` at 6:00 AM. **The installed crontab labels four different universes between 07:00 and 07:36 ET.** `docker/jobs.yaml` is a reference file and can also lag.

The habit to build: **verify the running configuration, not the documentation** — including this document.

```bash
docker exec quant-hub cat /etc/cron.d/quant-hub
```
