from __future__ import annotations

import pandas as pd

from quant_hub.config import RAW_SCORE_MAX
from quant_hub.engine.types import TickerResult
from quant_hub.regime.market import MarketRegime
from quant_hub.strategies.breakout.tiers import assign_tier_from_row

BREAKOUT_SCORE_COLUMNS = [
    "rs_market_score",
    "rs_sector_score",
    "accumulation_score",
    "relative_volume_score",
    "compression_score",
    "pattern_score",
    "resistance_score",
]


def aggregate_breakout_ticker(ticker: TickerResult, regime: MarketRegime) -> TickerResult:
    raw = sum(fr.score for fr in ticker.factors.values())
    penalty = sum(ticker.penalties.values())
    raw = max(0.0, raw + penalty)
    ticker.raw_score = raw
    ticker.normalized_score = (raw / float(RAW_SCORE_MAX)) * 100 if RAW_SCORE_MAX else 0.0
    ticker.regime_multiplier = regime.multiplier
    ticker.final_score = ticker.normalized_score * regime.multiplier
    return ticker


def build_results_table(
    rows: list[dict],
    regime: MarketRegime,
) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    for col in BREAKOUT_SCORE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = df[col].fillna(0.0)

    df["raw_score"] = df[BREAKOUT_SCORE_COLUMNS].sum(axis=1)
    df["normalized_score"] = (df["raw_score"] / RAW_SCORE_MAX) * 100
    df["regime_multiplier"] = regime.multiplier
    df["final_adjusted_score"] = df["normalized_score"] * regime.multiplier
    df["tier"] = df.apply(assign_tier_from_row, axis=1)

    eligible = df[df["eligible"]].copy()
    filtered = df[~df["eligible"]].copy()

    eligible = eligible.sort_values(
        by=["final_adjusted_score", "rs_market_score", "accumulation_score"],
        ascending=[False, False, False],
    )
    filtered = filtered.sort_values(by="ticker")

    return pd.concat([eligible, filtered], ignore_index=True)
