"""Launchpad factor research helpers on synthetic runs (no DB)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_hub.research import launchpad_factors as lf


def _panel(n_runs: int = 12, n: int = 30, signal: float = 1.0) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for r in range(n_runs):
        day = pd.Timestamp("2024-01-06") + pd.Timedelta(weeks=r)
        x = rng.normal(size=n)
        fwd = signal * x + rng.normal(scale=0.5, size=n)
        for i in range(n):
            rows.append({"run_id": r, "scan_date": day, "universe_id": "u", "ticker": f"T{i}",
                         "eligible": True, "tier": "Tier 3", "f": x[i], "fwd": fwd[i]})
    df = pd.DataFrame(rows)
    df["fwd_rel"] = df["fwd"] - df.groupby("run_id")["fwd"].transform("mean")
    return df


def test_run_level_ic_and_spread_detect_signal():
    runs = lf.run_level(_panel(signal=1.0), "f")
    assert len(runs) == 12
    assert (runs["ic"] > 0.5).all()
    assert (runs["q5_minus_q1"] > 0).all()


def test_noise_factor_has_no_ic():
    runs = lf.run_level(_panel(signal=0.0), "f")
    assert abs(runs["ic"].mean()) < 0.15


def test_non_overlapping_keeps_every_kth_weekly_run():
    runs = lf.run_level(_panel(n_runs=12), "f")
    assert len(lf.non_overlapping(runs, horizon=20)) == 3  # every 4th week
    assert len(lf.non_overlapping(runs, horizon=5)) == 12


def test_factor_table_splits_design_and_holdout():
    table = lf.factor_table(_panel(n_runs=12), ["f"], 5, lf.default_splits("2024-02-15"))
    by = table.set_index("period")
    assert by.loc["design", "indep_runs"] + by.loc["holdout", "indep_runs"] == 12
    assert by.loc["design", "mean_ic"] > 0.5
