
# How ML currently works in quant-hub

In quant-hub, ML operates as a post-scan evaluator via quant-ml commands:Feature Engineering (src/quant_hub/ml/features.py): Converts technical price action (volatility, momentum, volume dry-ups) into a numerical feature matrix $X$.Labeling (src/quant_hub/ml/labels.py): 

Computes forward returns $Y$ (e.g., Did NVDA outperform SPY by 5% over the next 10 trading days?).Walk-Forward Cross-Validation (src/quant_hub/ml/walk_forward.py): Trains models (like LightGBM or Scikit-Learn Random Forests) on past data and tests them on unseen future slices.2. Four Hands-On ML Projects You Can Build in quant-hub

# Project 1:  Add a Model-Based "Probability of Success" Badge to Launchpad

The Learning Goal: Binary Classification & Feature Importance.The Idea: Launchpad ranks stocks using hardcoded rule tiers (Tier 1 vs Tier 2). You can train a model (like HistGradientBoostingClassifier) on historical Launchpad picks to predict if a Tier 1 stock actually gains $\ge 5\%$ over the next 10 days.


`features.py` and `train.py` are **offline ML helpers**. They were built to flatten **already-saved scan JSON** and to **fit/save/load** LightGBM. Live `ScanService` never calls them today. You can reuse them for inference if you hook **after** `build_scan_report()` and write the probability into the report dict that Postgres already stores as `ticker_results.detail`.

---

# 1. What `features.py` does

This file does **not** talk to Yahoo, LightGBM, or `TickerResult`. It turns one persisted ticker document plus one scan-run row into a **flat dict** (one ML example).

### Helpers

| Function | Job |
|----------|-----|
| `_categories_str` | Lynch only: `["fast_grower", "stalwart"]` → `"fast_grower,stalwart"` |
| `_score_from_block` | Read `scores["squeeze_intensity"]["score"]`, or the flat key `squeeze_intensity_score` |
| `_raw_from_block` | Read a number **inside** `scores[name]["raw"][key]` — this is what training actually uses |

`_raw_from_block` is the important one. Training features are **not** the 0–40 point scores. They are the **raw measurements** sitting under `raw`:

```32:43:src/quant_hub/ml/features.py
def _raw_from_block(scores: dict, name: str, key: str) -> float | None:
    """Pull a numeric field from scores[name].raw (Launchpad factor detail payload)."""
    block = scores.get(name)
    if not isinstance(block, dict):
        return None
    raw = block.get("raw")
    if not isinstance(raw, dict) or key not in raw:
        return None
    try:
        return float(raw[key])
    except (TypeError, ValueError):
        return None
```

That matches how `launchpad_score_components_detail` writes the report:

```33:38:src/quant_hub/report/launchpad_diagnostics.py
    return {
        ...
        "squeeze_intensity": {
            "score": ...,
            "max": 40,
            "raw": squeeze_raw,   # {"squeeze_ratio": 0.87, ...}
```

### `extract_features(strategy_id, detail, run)`

**Inputs**

- `detail`: one ticker’s report blob (same shape as `ticker_results.detail`).
- `run`: scan-run metadata (`id`, `scan_date`, `universe_id`, `regime_multiplier`, `metadata`, …).

**Output:** one Python `dict` (not a DataFrame). Extra diagnostic keys are included; the model only uses `LAUNCHPAD_FEATURE_COLUMNS` from `ml/constants.py`:

| Feature column | Pulled from |
|----------------|-------------|
| `final_score` | `detail["summary"]["final_adjusted_score"]` |
| `volatility_compression_ratio` | `scores.squeeze_intensity.raw.squeeze_ratio` |
| `relative_strength_rank` | `scores.tightness_percentile.raw.tightness_rank_pct` |
| `volume_rs_score` | `scores.volume_vacuum_depth.raw.rvol` |
| `resistance_distance_pct` | `scores.trend_proximity_match.raw.pct_distance` |
| `market_regime_multiplier` | `run["regime_multiplier"]` |

`eligible` is rewritten as `1.0` / `0.0` for export, but it is **not** in `LAUNCHPAD_FEATURE_COLUMNS`.

`merge_outcome_columns` only attaches **labels** (`forward_return_pct`, `label_binary`, …). Do **not** call that at scan time — those are future prices.

---

# 2. What `train.py` does

Three jobs: **fit**, **save**, **load**. No scan logic.

### Defaults

`DEFAULT_LGBM_PARAMS` trains a **binary classifier** (`objective: "binary"`). The target is `label_binary`: “did forward return ≥ ~2% over the chosen horizon?”

### `train_lightgbm_classifier(X, y)`

```28:43:src/quant_hub/ml/train.py
def train_lightgbm_classifier(X, y, *, params=None):
    merged = {**DEFAULT_LGBM_PARAMS, **(params or {})}
    train_data = lgb.Dataset(X, label=y)
    booster = lgb.train(merged, train_data, num_boost_round=...)
    return booster
```

- `X`: pandas DataFrame, **only** the feature columns, all floats.
- `y`: pandas Series of `0`/`1`.
- Returns a LightGBM `Booster`.

`{**a, **b}` means “copy default params, then overwrite with any extras.”

### `save_model_artifact` / `load_model_artifact`

On disk (under `data/ml/models/<name>/`, from `ML_MODELS_DIR`):

```
model.txt        # LightGBM trees
features.json    # {"feature_columns": [...], "strategy_id", "universe_id", "horizon_days"}
```

```65:71:src/quant_hub/ml/train.py
def load_model_artifact(artifact_dir):
    booster = lgb.Booster(model_file=str(path / "model.txt"))
    meta = json.loads((path / "features.json").read_text())
    return booster, list(meta["feature_columns"])
```

`MLTrainService` also inserts a row in `ml_models` with `artifact_path` pointing at that **directory**. `MlModelsRepository.list_models(...)` is `ORDER BY created_at DESC`.

**Predict (already used in training/eval):**

```python
probs = booster.predict(X)   # numpy array, length = n_rows
```

For `objective="binary"` this is **P(class 1)** in about `[0, 1]`, not a raw margin. That is your `ml_probability_score`.

---

# 3. Why you should not score inside `StrategyEngine`

`TickerResult.factors["squeeze_intensity"].details` is the **raw dict** (`squeeze_ratio` at the top level).

`extract_features` expects the **report** shape: `scores["squeeze_intensity"]["raw"]["squeeze_ratio"]`.

`ScanService` already builds that report **before** Postgres:

```84:130:src/quant_hub/application/scan_service.py
            scan_result = engine.run()
            ...
            scan_report = build_scan_report(...)
            if persist:
                run_id = self.scan_repo.upsert_scan(..., report=scan_report)
```

`upsert_scan` writes each `report["tickers"][i]` into `detail` JSONB. There is **no** `ml_probability_score` column. Put the number on that ticker dict and it is saved automatically.

`TickerResult` also has no probability field. You can use `metadata` if you want it on the object; Postgres will not see that unless it is copied into the report.

---

# 4. Recommended design

```
engine.run()
   → build_scan_report()          # scores.*.raw now exist
   → attach_ml_probabilities()    # NEW: extract_features + booster.predict
   → upsert_scan(report)          # detail JSONB includes ml_probability_score
```

Keep `ScanService` thin: load the model once, call a small helper. Same helper can later be used from `LaunchpadBackfillService._backfill_one_date` (same report path).

### Step A — Resolve which model to load

```python
# Sketch — new helper, e.g. quant_hub/ml/inference.py

from pathlib import Path
from quant_hub.infrastructure.postgres.ml_models_repository import MlModelsRepository
from quant_hub.ml.train import load_model_artifact
from quant_hub.config import FEATURE_SCHEMA_VERSION

def load_active_launchpad_model(*, universe_id: str, horizon_days: int | None = None):
    repo = MlModelsRepository()
    models = repo.list_models(
        strategy_id="launchpad",
        universe_id=universe_id,
        status="active",
        limit=20,
    )
    if horizon_days is not None:
        models = [m for m in models if m["horizon_days"] == horizon_days]
    if not models:
        return None
    record = models[0]  # newest first
    if record.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise RuntimeError("feature schema mismatch — retrain")
    booster, columns = load_model_artifact(Path(record["artifact_path"]))
    return booster, columns, record
```

Pick **universe + horizon** on purpose. A model trained on `mega_runners` / 20-day labels is a different question than `large_cap_growth` / 5-day.

### Step B — Build the same `X` the trainer used

After `build_scan_report`, each `ticker` dict **is** `detail`. Synthesize a `run` dict that `extract_features` understands (`run["id"]` can be `0` before persist):

```python
import pandas as pd
from quant_hub.ml.features import extract_features
from quant_hub.ml.constants import LAUNCHPAD_FEATURE_COLUMNS

def attach_ml_probabilities(scan_report: dict, *, booster, feature_columns, run_stub: dict) -> None:
    rows = []
    tickers = scan_report["tickers"]
    for t in tickers:
        feat = extract_features(strategy_id="launchpad", detail=t, run=run_stub)
        rows.append(feat)

    frame = pd.DataFrame(rows)
    # Same columns, same order as training — LightGBM is order-sensitive
    X = frame[list(feature_columns)].apply(pd.to_numeric, errors="coerce")

    usable = X.notna().all(axis=1)
    probs = [None] * len(tickers)
    if usable.any():
        pred = booster.predict(X.loc[usable])  # P(label_binary == 1)
        for i, p in zip(X.index[usable], pred):
            probs[i] = float(p)

    for t, p in zip(tickers, probs):
        t["ml_probability_score"] = p  # None if any feature was missing
        t.setdefault("summary", {})["ml_probability_score"] = p
```

`run_stub` example from `ScanService` after the report exists:

```python
run_stub = {
    "id": 0,
    "scan_date": scan_date,
    "scan_time": "",
    "strategy_id": "launchpad",
    "universe_id": resolved_id,
    "universe_size": len(scan_result.universe),
    "regime_label": scan_result.regime.label,
    "regime_multiplier": scan_report["market_regime"].get("multiplier", 1.0),
    "metadata": {"data_provenance": scan_report.get("data_provenance") or {}},
}
```

`market_regime_multiplier` is the only feature that comes from `run`, not from `detail`. Get it wrong and every probability is off.

### Step C — Call it from `ScanService.run` (only Launchpad)

```python
# After scan_report = build_scan_report(...)
# Before upsert_scan(...)

loaded = load_active_launchpad_model(universe_id=resolved_id)
if loaded is not None:
    booster, columns, record = loaded
    attach_ml_probabilities(
        scan_report,
        booster=booster,
        feature_columns=columns,
        run_stub=run_stub,
    )
    scan_report.setdefault("data_provenance", {})["ml_model_id"] = record["id"]
    scan_report["data_provenance"]["ml_model_name"] = record["name"]
```

`upsert_scan` already JSON-dumps each ticker. No schema migration required.

Optional extras (not required to persist):

- `TickerResult.metadata["ml_probability_score"]` — only if something else reads the object.
- `to_row_dict()` — only if you want it in the CSV.
- A real `ticker_results.ml_probability_score` column — only if you want SQL `ORDER BY` without digging into JSONB.

---

# 5. If you insist on attaching to `TickerResult` *before* the report

You would skip `extract_features` and read `FactorResult.details` directly (no `"raw"` wrapper):

```python
tr.factors["squeeze_intensity"].details.get("squeeze_ratio")
tr.factors["tightness_percentile"].details.get("tightness_rank_pct")
tr.factors["volume_vacuum_depth"].details.get("rvol")
tr.factors["trend_proximity_match"].details.get("pct_distance")
tr.final_score
tr.regime_multiplier
```

Then you still must copy the probability into `scan_report["tickers"]` or `build_ticker_report` will drop it. Prefer the report-based path so training and live inference share one function.

---

# 6. Beginner pitfalls (this will bite you)

1. **Missing model** — `list_models` is empty until `quant-ml train` has run. Treat that as “no score,” not a crash.

2. **NaN features** — training **drops** any row with a missing feature (`training_set.py`). If history is too short, `score_*` returns `{}` and `_raw_from_block` is `None`. Predict only on complete rows; leave `ml_probability_score = None` on the rest.

3. **`setups_only=True`** — the model was trained on Tier 1/2/3 only, not `filtered`. Scoring ineligible names is out-of-distribution. Safer: only attach a probability when `t["eligible"]` is true (or `t["tier"]` in `LAUNCHPAD_SETUP_TIERS`).

4. **Do not change `final_score` or tier** with this number unless you explicitly want a reranker. Docs still say live inference is not approved. Start by **storing** the probability.

5. **What 0.73 means** — “model’s estimated P(forward return ≥ threshold over `horizon_days`)”, not “73 Launchpad points.” Different horizons are different models.

6. **`FEATURE_SCHEMA_VERSION`** (`v4` in config) — if you change `extract_features` mappings, old `model.txt` is invalid. Refuse to load on mismatch.

7. **LightGBM optional extra** — `pyproject.toml` puts `lightgbm` in `[ml]`. The Docker image installs `[dev,viz,ml]`. A bare local install without that extra will fail on `import lightgbm`.

8. **Backfill** — if you only hook `ScanService`, Saturday backfills stay unscored. Mirror the same three lines in `_backfill_one_date`.

---

# 7. How this maps to “load in ScanService”

| You want | Use this existing piece |
|----------|-------------------------|
| Load trees + column list | `load_model_artifact(dir)` in `train.py` |
| Find `dir` for this universe | `MlModelsRepository.list_models(...)` |
| Same features as training | `extract_features` on `scan_report["tickers"]` |
| Probability in `[0, 1]` | `booster.predict(X)` |
| Save to Postgres | Set `ticker["ml_probability_score"]` before `upsert_scan` |

`evaluate_service.py` already does load + `booster.predict` on a holdout frame. Copy that pattern; point it at the live report instead of a historical training set.

I'm in Ask mode so I can’t apply this. If you switch to Agent mode, a clean first PR is: new `ml/inference.py` + a few lines in `ScanService` (and later backfill), **without** changing tiers.


# Project 2: Market Regime Classification (Unsupervised Clustering)

The Learning Goal: Unsupervised Learning (KMeans or Gaussian Mixture Models).

The Idea: Currently, market regime (Bullish/Bearish/Volatile) uses simple moving averages on SPY. You can train a KMeans clustering model on SPY & VIX metrics (realized volatility, ATR, volume spread) to automatically discover 3–4 hidden market regimes.

# How `compute_market_regime` works today

It does **not** look at NVDA or any scanned ticker. It looks only at **SPY’s daily OHLCV** (`spy_df`) and answers: “is the *market* strong, weak, or mixed?”

```14:17:src/quant_hub/regime/market.py
def compute_market_regime(spy_df: pd.DataFrame) -> MarketRegime:
    """Classify SPY market regime and return score multiplier."""
    detail = regime_detail(spy_df)
    return MarketRegime(detail["label"], detail["multiplier"])
```

`MarketRegime` is a tiny frozen dataclass: `label` (`"strong"` / `"neutral"` / `"weak"`) and `multiplier` (`1.0` / `0.85` / `0.6`).

All of the rules live in `regime_detail`.

---

## Inputs (pandas)

`spy_df` is a DataFrame of **SPY bars**, one row per trading day, at least columns `Close` and `High`. The last row is “today” (or the backfill Saturday after truncation).

| Line | What it computes | Plain English |
|------|------------------|---------------|
| `close.iloc[-1]` | last close | SPY’s latest price |
| `sma(close, 50).iloc[-1]` | 50-day **simple moving average** | `rolling(50).mean()` — average of the last 50 closes |
| `sma(close, 200).iloc[-1]` | 200-day SMA | classic “long-term trend” line |
| `return_over_days(close, 63)` | ~3-month return | `(last / close_63_days_ago) - 1` (a fraction, e.g. `0.08` = +8%) |
| `High.tail(252).max()` | 52-week high | highest High in the last ~252 trading days |
| `distance_from_high_pct` | drawdown from that high | `(high - price) / high` |

If there are not enough bars, `return_over_days` can return `None` and is treated as `0.0`. SMA with `min_periods=window` is `NaN` until you have 50/200 days — the current code then does `float(...)` on that, so a short SPY series can throw. Live scans always also download SPY with a long lookback, so this rarely happens.

---

## The three if/else rules

```31:42:src/quant_hub/regime/market.py
    strong = price > sma50 and sma50 > sma200 and ret_63 > 0
    weak = price < sma200 or dist_from_high > 0.10

    if strong:
        label, multiplier = "strong", 1.0
    elif weak:
        label, multiplier = "weak", 0.6
    else:
        label, multiplier = "neutral", 0.85
```

In words:

1. **Strong** — price above the 50-day, 50-day above the 200-day (uptrend stack), **and** the last 63 days were positive. Multiplier **1.0** (no discount).
2. Else **weak** — price below the 200-day **or** more than 10% off the 52-week high. Multiplier **0.6**.
3. Else **neutral**. Multiplier **0.85**.

`strong` is checked first, so a market that is both “stacked SMA” *and* 11% off highs is still **strong**.

`regime_detail` also returns a dict for the dashboard/Postgres (`meaning`, `spy_price`, SMAs, `return_63d_pct`, `pct_below_52w_high`). `compute_market_regime` only keeps `label` + `multiplier`.

---

## Where it is called, and what it does *not* do

`ScanContext.from_universe` / `from_prices` call both functions and stash them on the context. The engine copies `regime_detail` onto the scan report.

**Launchpad does not multiply scores by this today.** `LAUNCHPAD_STRATEGY` has `regime_mode="none"`, and `aggregate_launchpad_ticker` ignores the `regime` argument and hard-sets `regime_multiplier = 1.0`.

So the rules still **label** the market (dashboard, digest, ML feature `market_regime_multiplier` from the **stored run**, which is usually 1.0 for Launchpad). Digest policy treats `label == "weak"` specially (Tier 2 suppression). Changing labels without updating `digest/policy.py` (`WEAK_REGIME_LABEL = "weak"`) will break that.

---

# Replacing the rules with scikit-learn `KMeans`

KMeans is **unsupervised**: you do not tell it “this day is strong.” You give it numbers (returns + volatility). It finds **K blobs** in that 2D space. You then **name** those blobs after the fact.

That is a different question than the SMA stack. Clustering asks “which *kind* of return/vol weather is today like?” Rules ask “are we above the 200-day?”

## 1. Features (what you train on)

For each SPY day `t`, build a small row. Typical pair:

```text
daily_return_t     = Close_t / Close_{t-1} - 1
volatility_t       = std(daily_return over last N days)   e.g. N = 20
```

Pandas:

```python
close = spy_df["Close"]
daily_ret = close.pct_change()                    # Series: one return per day
vol_20 = daily_ret.rolling(20, min_periods=20).std()  # realized vol

X = pd.DataFrame({
    "daily_return": daily_ret,
    "volatility": vol_20,
}).dropna()   # first ~20 rows are NaN — drop them
```

You can add more columns (63-day return, distance from high) so clusters look more like today’s rules. Start with two so you can **scatter-plot** return vs vol and *see* the clusters.

**Scale the columns.** Returns are ~0.01; vol is a different size. KMeans uses Euclidean distance, so without scaling, the bigger-magnitude feature dominates.

```python
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)   # fit on HISTORY only
# X_scaled is a NumPy array, shape (n_days, 2), mean~0, std~1 per column
```

`fit_transform` = **fit** (learn mean/std of each column) then **transform** (subtract mean, divide by std). At scan time you only call `scaler.transform(new_row)` — never `fit` again on one day.

## 2. Train KMeans (offline, once)

```python
kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
kmeans.fit(X_scaled)
```

- `n_clusters=3` matches strong / neutral / weak, but the IDs `0, 1, 2` are **arbitrary**. Cluster `0` is not “strong.”
- `n_init=10` reruns with different starting centers; keeps the best (inertia).
- `kmeans.labels_` is an array of ints, one per training day.
- `kmeans.cluster_centers_` is the center of each blob **in scaled space**.

Persist both objects (same idea as LightGBM’s `model.txt`):

```python
import joblib
joblib.dump({"scaler": scaler, "kmeans": kmeans, "label_map": label_map},
            "data/ml/models/spy_regime_kmeans.joblib")
```

Train on a **long** SPY history (the 5y ML cache is a natural source), not on the last 200 days of a live scan.

## 3. The hard part: name the clusters

After `fit`, look at each cluster’s **unscaled** average return and vol:

```python
X.assign(cluster=kmeans.labels_).groupby("cluster")[["daily_return", "volatility"]].mean()
```

A reasonable naming rule (you choose this; KMeans will not):

| Typical centroid | Name you assign | Multiplier you assign |
|------------------|-----------------|------------------------|
| High return, low/medium vol | `strong` | `1.0` |
| Low/negative return, high vol | `weak` | `0.6` |
| The leftover blob | `neutral` | `0.85` |

Save that as `label_map = {2: ("strong", 1.0), 0: ("weak", 0.6), 1: ("neutral", 0.85)}`.

Re-fit KMeans and the integer IDs can **swap**. Always remap from centroids, or freeze the saved `label_map` with that artifact.

## 4. Use it at scan time (drop-in for `compute_market_regime`)

Keep the same **return types** so `ScanContext` does not change:

```python
def compute_market_regime(spy_df: pd.DataFrame) -> MarketRegime:
    detail = regime_detail(spy_df)
    return MarketRegime(detail["label"], detail["multiplier"])
```

Inside `regime_detail`:

1. Load the saved `{scaler, kmeans, label_map}` (cache in memory so every ticker doesn’t reload the file).
2. From **the last rows of `spy_df` only**, compute the same `daily_return` and `volatility` as training.
3. `x = scaler.transform([[ret, vol]])` — shape `(1, 2)`.
4. `cluster_id = int(kmeans.predict(x)[0])` — nearest centroid.
5. `label, multiplier = label_map[cluster_id]`.
6. Still return the extra diagnostic fields (price, SMAs) if the dashboard expects them; add `cluster_id` and the two features so you can debug.

For **backfill**, `spy_df` is already truncated to `scan_date`. As long as features use only that frame, you do not peek at the future. Do **not** refit KMeans inside each Saturday.

## 5. Suggested file split (so live scans stay simple)

| Piece | Role |
|-------|------|
| `scripts/` or `quant-ml` subcommand | Download SPY, build `X`, `fit` scaler + KMeans, write joblib + label_map |
| `regime/market.py` | Load artifact, `predict` last day, return `MarketRegime` |
| Tests | Fixed toy `spy_df` → known cluster after you freeze a tiny fixture model |

Do not call `KMeans.fit` inside `ScanContext.from_universe`. Fitting on ~250 live bars is unstable and **changes cluster IDs** every scan.

## 6. What you must keep compatible

- **`label` strings** — digest uses `"weak"`. If you emit `"cluster_2"` or `"high_vol"`, update `WEAK_REGIME_LABEL` and tests.
- **`multiplier`** — unused for Launchpad *scores* today, but stored on `scan_runs.regime_multiplier` and as ML feature `market_regime_multiplier`. New values change that feature for future models.
- **`regime_detail` keys** — dashboard/tests expect `label`, `multiplier`, `spy_price`, etc. Add fields; don’t rename old ones without checking `test_repository.py` / digest.

## 7. Why KMeans vs the current rules (and vs alternatives)

| Approach | Strength | Weakness here |
|----------|----------|----------------|
| **Current SMA rules** | Interpretable (“below 200-day”); stable | Ignores volatility; sharp cliff at 10% off highs |
| **KMeans on return + vol** | Finds “calm up / chop / crash” blobs from data; sklearn is small and already a project extra | Cluster IDs are meaningless until you map them; sensitive to scaling and `K`; no time structure (day 100 and day 1 are independent points) |
| **HMM / GMM** | Regimes that *persist* over time | More moving parts; not what you asked for |
| **Supervised classifier** | You could label days yourself (or use recession dates) | Needs labels; different problem |

KMeans will **not** reproduce the SMA rule. A melt-up with rising vol can land in the “high vol” blob even if price is above the 200-day. That is expected.

## 8. Mini checklist if you implement this

1. Build a training table of SPY `daily_return` + `rolling vol`; `dropna`.
2. `StandardScaler.fit_transform` → `KMeans(n_clusters=3).fit`.
3. `groupby(cluster).mean()` and write a `label_map` to `strong` / `neutral` / `weak`.
4. `joblib.dump` scaler + kmeans + map.
5. Replace only the *classification* inside `regime_detail`; keep `MarketRegime(label, multiplier)`.
6. At inference: last-day features → `transform` → `predict` → map.
7. Re-check digest weak-regime behavior and `test_ml_features.py` (it hard-codes multiplier `0.85`).

I'm in Ask mode, so this is the design only. If you want it coded, Agent mode plus a small train script and a `regime_detail` load/predict path is the smallest change that stays compatible with `ScanContext`.

# Project 3: Automated Feature Importance & SHAP Analysis
The Learning Goal: Model Explainability (SHAP / Feature Importance).

The Idea: In Machine Learning, knowing why a model made a prediction is critical. You can extract feature importance weights to answer: Is Volume Vacuum or Bollinger Squeeze more predictive of a coiled spring breakout?

`evaluate.py` has no importance helper today. The only place it exists is inline in `MLTrainService`:

```114:118:src/quant_hub/application/ml_train_service.py
        importance = booster.feature_importance(importance_type="gain")
        stats.feature_importance = {
            col: float(importance[i])
            for i, col in enumerate(result.feature_columns)
        }
```

One correction on the plan: the feature **names** don't live in `features.py`. That file produces a flat dict whose *keys* match the canonical tuple in `ml/constants.py`:

```20:27:src/quant_hub/ml/constants.py
LAUNCHPAD_FEATURE_COLUMNS = (
    "final_score",
    "volatility_compression_ratio",
    "relative_strength_rank",
    "volume_rs_score",
    "resistance_distance_pct",
    "market_regime_multiplier",
)
```

The trained model's own copy is saved in `features.json` and returned by `load_model_artifact`. **Prefer that list** — it is the exact order the booster was fit on. `features.py` guarantees those keys exist in each row; `constants.py` guarantees the order.

---

## The function

Ask mode, so this isn't applied. Paste it near the bottom of `src/quant_hub/ml/evaluate.py` (it matches the file's existing `numpy` + `pandas` imports; add `Sequence` to the imports).

```python
from collections.abc import Sequence  # add to the existing imports


def _raw_importances(booster: Any, importance_type: str) -> np.ndarray:
    """Pull the importance vector off a LightGBM Booster or sklearn estimator."""
    if hasattr(booster, "feature_importance"):  # lightgbm.Booster
        raw = booster.feature_importance(importance_type=importance_type)
    elif hasattr(booster, "feature_importances_"):  # sklearn-style
        raw = booster.feature_importances_
    else:
        raise TypeError(f"{type(booster).__name__} exposes no feature importances")
    return np.asarray(raw, dtype=float)


def _resolve_feature_names(
    booster: Any,
    feature_columns: Sequence[str] | None,
    n_features: int,
) -> list[str]:
    """Prefer the artifact's saved columns; fall back to the booster's own names."""
    if feature_columns is not None:
        names = list(feature_columns)
    else:
        getter = getattr(booster, "feature_name", None)
        names = list(getter()) if callable(getter) else []
    if len(names) != n_features:
        # Never let a name/vector mismatch silently mislabel a factor.
        names = [names[i] if i < len(names) else f"feature_{i}" for i in range(n_features)]
    return names


def feature_importance_frame(
    booster: Any,
    feature_columns: Sequence[str] | None = None,
    *,
    importance_type: str = "gain",
    top_n: int | None = 10,
) -> pd.DataFrame:
    """
    Rank a trained model's features by importance.

    Args:
        booster: Trained LightGBM Booster (or any estimator with
            `feature_importances_`).
        feature_columns: Column order used at fit time — normally the second
            value from `load_model_artifact()`, or `LAUNCHPAD_FEATURE_COLUMNS`.
            `None` falls back to `booster.feature_name()`.
        importance_type: LightGBM metric. `"gain"` = total loss reduction the
            feature contributed (what you usually want). `"split"` = how many
            times it was used to split.
        top_n: Keep only the N strongest rows. `None` keeps all.

    Returns:
        DataFrame with columns `rank`, `feature`, `importance`,
        `importance_pct`, sorted strongest first.
    """
    values = _raw_importances(booster, importance_type)
    names = _resolve_feature_names(booster, feature_columns, len(values))

    frame = pd.DataFrame({"feature": names, "importance": values})
    total = float(frame["importance"].sum())
    frame["importance_pct"] = (frame["importance"] / total * 100.0) if total > 0 else 0.0

    frame = frame.sort_values("importance", ascending=False, ignore_index=True)
    if top_n is not None:
        frame = frame.head(top_n).copy()

    frame.insert(0, "rank", np.arange(1, len(frame) + 1))
    frame["importance"] = frame["importance"].round(4)
    frame["importance_pct"] = frame["importance_pct"].round(2)
    return frame
```

Because `MLTrainService` already persists the same numbers into `ml_models.metrics`, a companion that skips reloading the artifact is useful:

```python
def feature_importance_frame_from_metrics(
    metrics: dict[str, Any] | None,
    *,
    top_n: int | None = 10,
) -> pd.DataFrame:
    """Same ranking, read from a registered model's stored `metrics` JSONB."""
    raw = (metrics or {}).get("feature_importance") or {}
    frame = pd.DataFrame(
        {"feature": list(raw.keys()), "importance": [float(v) for v in raw.values()]}
    )
    if frame.empty:
        return pd.DataFrame(columns=["rank", "feature", "importance", "importance_pct"])

    total = float(frame["importance"].sum())
    frame["importance_pct"] = (frame["importance"] / total * 100.0) if total > 0 else 0.0
    frame = frame.sort_values("importance", ascending=False, ignore_index=True)
    if top_n is not None:
        frame = frame.head(top_n).copy()
    frame.insert(0, "rank", np.arange(1, len(frame) + 1))
    frame["importance"] = frame["importance"].round(4)
    frame["importance_pct"] = frame["importance_pct"].round(2)
    return frame
```

---

## Using it

From a saved artifact (the pattern `MLEvaluateService` already uses on line 142):

```python
from quant_hub.ml.train import load_model_artifact
from quant_hub.ml.evaluate import feature_importance_frame

booster, feature_columns = load_model_artifact("data/ml/models/launchpad_mega_runners_h20_20260905")
top = feature_importance_frame(booster, feature_columns, top_n=10)
print(top.to_string(index=False))
```

From the registry, no files touched:

```python
from quant_hub.infrastructure.postgres.ml_models_repository import MlModelsRepository
from quant_hub.ml.evaluate import feature_importance_frame_from_metrics

record = MlModelsRepository().get_by_id(3)
print(feature_importance_frame_from_metrics(record["metrics"]))
```

Typical output:

```
 rank                        feature  importance  importance_pct
    1                    final_score    412.7031           38.15
    2  volatility_compression_ratio    255.4410           23.61
    3                volume_rs_score    198.0022           18.30
    4       resistance_distance_pct    121.8890           11.27
    5        relative_strength_rank     94.2255            8.71
    6      market_regime_multiplier      0.0000            0.00
```

---

## Four things that will surprise you

**Top 10 will return 6 rows.** Launchpad trains on exactly six features. `top_n=10` is harmless (`.head()` doesn't pad), but the "top 10 factors" framing only becomes meaningful if you widen `LAUNCHPAD_FEATURE_COLUMNS`.

**`market_regime_multiplier` is likely 0.** `aggregate_launchpad_ticker` hard-sets `regime_multiplier = 1.0`, so that column is constant and LightGBM never splits on it. Zero importance here means "no variance," not "regime doesn't matter."

**Gain vs split disagree.** `"gain"` rewards features that reduce loss a lot in a few splits; `"split"` rewards frequently-used ones. Continuous features like `squeeze_ratio` inflate `"split"` counts. Report `"gain"` unless you're debugging tree structure.

**Importance is not causality, and it's unstable on small data.** With a few hundred rows the ranking can reshuffle between folds. If you want a claim you'd act on, run `feature_importance_frame` per walk-forward fold in `MLEvaluateService` and average the `importance_pct` column — that's a natural follow-up if you want me to sketch it.