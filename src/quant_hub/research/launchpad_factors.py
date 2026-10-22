"""Launchpad factor research: which stored factors (and the rubric) predict forward returns?

Unit of evidence is one scan run (date x universe). Inside a run:
- a factor's rank IC is the Spearman correlation between the factor and the forward return,
  across the run's *eligible* tickers;
- a quintile spread is (top-quintile mean - bottom-quintile mean) forward return.
Runs are then aggregated, and t-stats use runs sampled so that, within a universe, forward
windows do not overlap (every ceil(h/5)-th weekly run). Only Saturday backfill runs are used
for design/holdout so the spacing is weekly and the scans are point-in-time.

Benchmarks computed from the price cache (not part of the rubric): 6-month momentum, 12-1
momentum, and distance below the 52-week high.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_hub.infrastructure.cache.parquet_cache import ParquetCache
from quant_hub.infrastructure.postgres.connection import get_connection

PANEL_SQL = """
select r.id as run_id, r.scan_date, r.universe_id, t.ticker, t.eligible, t.tier, t.final_score,
       r.metadata->'data_provenance'->>'as_of_price' as as_of_price,
       coalesce((r.metadata->'data_provenance'->>'backfill')::boolean, false) as backfill,
       o.forward_return_pct as fwd,
       (s->'squeeze_intensity'->>'score')::float as sc_squeeze,
       (s->'tightness_percentile'->>'score')::float as sc_tightness,
       (s->'volume_vacuum_depth'->>'score')::float as sc_volume,
       (s->'trend_proximity_match'->>'score')::float as sc_trend,
       (s->'macd_zero_line'->>'score')::float as sc_macd,
       (s->'squeeze_intensity'->'raw'->>'squeeze_ratio')::float as squeeze_ratio,
       (s->'volume_vacuum_depth'->'raw'->>'rvol')::float as rvol,
       (s->'tightness_percentile'->'raw'->>'tightness_rank_pct')::float as tightness_rank,
       (s->'trend_proximity_match'->'raw'->>'pct_distance')::float as dist_ema50,
       (s->'trend_proximity_match'->'raw'->>'rs_score')::float as rs_score,
       (s->'macd_zero_line'->'raw'->>'macd_line')::float as macd_line,
       (s->'macd_zero_line'->'raw'->>'macd_signal')::float as macd_signal
from signal_outcomes o
join scan_runs r on r.id = o.run_id
join ticker_results t on t.run_id = o.run_id and t.ticker = o.ticker
left join lateral (select t.detail->'scores' as s) x on true
where r.strategy_id = 'launchpad' and o.horizon_days = %(h)s
  and o.label_status = 'ok' and o.forward_return_pct is not null
"""

# Columns evaluated; "lower is better" ones show a negative IC when they work.
RUBRIC_COLUMNS = ["final_score", "sc_squeeze", "sc_tightness", "sc_volume", "sc_trend", "sc_macd"]
RAW_COLUMNS = ["squeeze_ratio", "rvol", "tightness_rank", "dist_ema50", "rs_score", "macd_hist"]
BENCHMARK_COLUMNS = ["mom_126", "mom_12_1", "off_52w_high"]


def load_panel(horizon: int) -> pd.DataFrame:
    with get_connection() as conn:
        df = pd.read_sql(PANEL_SQL, conn, params={"h": horizon})
    df["scan_date"] = pd.to_datetime(df["scan_date"])
    df["as_of_price"] = pd.to_datetime(
        df["as_of_price"].fillna(df["scan_date"].astype(str))
    ).astype("datetime64[ns]")
    df["macd_hist"] = df["macd_line"] - df["macd_signal"]
    # Clip each run's forward returns to its 2.5-97.5 percentile band so one meme spike or bad
    # print cannot dominate a mean; rank ICs are unaffected.
    grp = df.groupby("run_id")["fwd"]
    df["fwd"] = df["fwd"].clip(grp.transform(lambda x: x.quantile(0.025)),
                               grp.transform(lambda x: x.quantile(0.975)))
    df["fwd_rel"] = df["fwd"] - df.groupby("run_id")["fwd"].transform("mean")
    return df


def add_price_benchmarks(panel: pd.DataFrame, cache: ParquetCache) -> pd.DataFrame:
    """Momentum and 52-week-high distance as of each row's price date (point-in-time)."""
    parts = []
    for ticker, rows in panel.groupby("ticker"):
        px = cache.read(ticker)
        rows = rows.sort_values("as_of_price")
        if px is None or px.empty:
            parts.append(rows)
            continue
        px = px.assign(Date=pd.to_datetime(px["Date"]).astype("datetime64[ns]")).sort_values("Date")
        close, high = px["Close"].astype(float), px["High"].astype(float)
        feats = pd.DataFrame({
            "Date": px["Date"],
            "mom_126": close / close.shift(126) - 1,
            "mom_12_1": close.shift(21) / close.shift(252) - 1,
            "off_52w_high": close / high.rolling(252, min_periods=200).max() - 1,
        })
        parts.append(pd.merge_asof(rows, feats, left_on="as_of_price", right_on="Date",
                                   direction="backward").drop(columns="Date"))
    return pd.concat(parts, ignore_index=True)


def _spearman(a: pd.Series, b: pd.Series) -> float:
    ok = a.notna() & b.notna()
    if ok.sum() < 8 or a[ok].nunique() < 2:
        return float("nan")
    return float(a[ok].rank().corr(b[ok].rank()))


def run_level(panel: pd.DataFrame, column: str) -> pd.DataFrame:
    """Per run: IC and top-minus-bottom quintile spread among eligible tickers."""
    rows = []
    for run_id, g in panel[panel["eligible"]].groupby("run_id"):
        x, y = g[column], g["fwd"]
        ok = x.notna()
        spread = float("nan")
        if ok.sum() >= 10 and x[ok].nunique() >= 2:
            q = pd.qcut(x[ok].rank(method="first"), 5, labels=False)
            spread = float(y[ok][q == 4].mean() - y[ok][q == 0].mean())
        rows.append({"run_id": run_id, "scan_date": g["scan_date"].iloc[0],
                     "universe_id": g["universe_id"].iloc[0], "ic": _spearman(x, y),
                     "q5_minus_q1": spread, "n": int(ok.sum())})
    return pd.DataFrame(rows)


def non_overlapping(runs: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Keep every ceil(h/5)-th weekly run per universe so forward windows don't overlap."""
    step = max(1, math.ceil(horizon / 5))
    keep = []
    for _, g in runs.sort_values("scan_date").groupby("universe_id"):
        keep.append(g.iloc[::step])
    return pd.concat(keep) if keep else runs.iloc[0:0]


def _t(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std() > 0 else float("nan")


@dataclass(frozen=True)
class Split:
    name: str
    start: pd.Timestamp | None
    end: pd.Timestamp | None

    def mask(self, dates: pd.Series) -> pd.Series:
        m = pd.Series(True, index=dates.index)
        if self.start is not None:
            m &= dates >= self.start
        if self.end is not None:
            m &= dates < self.end
        return m


def factor_table(panel: pd.DataFrame, columns: list[str], horizon: int,
                 splits: list[Split]) -> pd.DataFrame:
    out = []
    for column in columns:
        runs = run_level(panel, column)
        if runs.empty:
            continue
        for split in splits:
            sel = non_overlapping(runs[split.mask(runs["scan_date"])], horizon)
            out.append({
                "factor": column, "period": split.name, "indep_runs": int(sel["ic"].notna().sum()),
                "mean_ic": sel["ic"].mean(), "ic_t": _t(sel["ic"]),
                "q5_minus_q1_pct": sel["q5_minus_q1"].mean(), "spread_t": _t(sel["q5_minus_q1"]),
            })
    return pd.DataFrame(out)


def tier_table(panel: pd.DataFrame, horizon: int, splits: list[Split]) -> pd.DataFrame:
    """Each tier's mean forward return relative to its run's universe mean."""
    per_run = (panel.groupby(["run_id", "scan_date", "universe_id", "tier"])["fwd_rel"]
               .mean().reset_index())
    out = []
    for split in splits:
        part = per_run[split.mask(per_run["scan_date"])]
        for tier, g in part.groupby("tier"):
            sel = non_overlapping(g, horizon)
            out.append({"tier": tier, "period": split.name, "indep_runs": len(sel),
                        "mean_rel_pct": sel["fwd_rel"].mean(), "t": _t(sel["fwd_rel"])})
    return pd.DataFrame(out)


def default_splits(holdout_start: str) -> list[Split]:
    cut = pd.Timestamp(holdout_start)
    return [Split("design", None, cut), Split("holdout", cut, None)]


def as_markdown(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, row in df.iterrows():
        cells = [f"{v:.3f}" if isinstance(v, float) and np.isfinite(v) else str(v) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _pct_rank(panel: pd.DataFrame, column: str, mask: pd.Series) -> pd.Series:
    """Percentile rank of ``column`` within each run, among rows where ``mask`` holds."""
    ranked = panel[column].where(mask).groupby(panel["run_id"]).rank(pct=True)
    return ranked.fillna(0.0)


def candidate_sets(panel: pd.DataFrame) -> dict[str, pd.Series]:
    """PR-2 candidates, frozen on the design period (see docs/research/LOG.md)."""
    elig = panel["eligible"].astype(bool)
    has_mom = panel["mom_126"].notna()
    return {
        "current_actionable": panel["tier"].isin(["Tier 1", "Tier 2"]),
        "C1_eligible_top_momentum": elig & (_pct_rank(panel, "mom_126", elig & has_mom) >= 0.8),
        "C2_universe_top_momentum": _pct_rank(panel, "mom_126", has_mom) >= 0.8,
        "C3_C1_with_squeeze": elig
        & (_pct_rank(panel, "mom_126", elig & has_mom) >= 0.8)
        & (panel["sc_squeeze"] >= 25),
    }


def candidate_table(panel: pd.DataFrame, horizon: int, splits: list[Split]) -> pd.DataFrame:
    """Each candidate set's mean (clipped) forward return minus its run's universe mean."""
    out = []
    for name, mask in candidate_sets(panel).items():
        per_run = (panel[mask].groupby(["run_id", "scan_date", "universe_id"])["fwd_rel"]
                   .agg(["mean", "size"]).reset_index())
        for split in splits:
            sel = non_overlapping(per_run[split.mask(per_run["scan_date"])], horizon)
            out.append({"candidate": name, "period": split.name, "indep_runs": len(sel),
                        "avg_names": sel["size"].mean(), "mean_rel_pct": sel["mean"].mean(),
                        "t": _t(sel["mean"])})
    return pd.DataFrame(out)
