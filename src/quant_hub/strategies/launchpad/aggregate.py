from __future__ import annotations

from quant_hub.config import LAUNCHPAD_RAW_SCORE_MAX
from quant_hub.engine.types import TickerResult
from quant_hub.regime.market import MarketRegime

# Factors that contribute to the 100-pt raw score (macd_zero_line is a Tier-1 gate only).
LAUNCHPAD_SCORE_FACTORS = frozenset(
    {
        "squeeze_intensity",
        "tightness_percentile",
        "volume_vacuum_depth",
        "trend_proximity_match",
    }
)

LAUNCHPAD_SCORE_COLUMNS = [
    "macd_zero_line_score",
    "squeeze_intensity_score",
    "tightness_percentile_score",
    "volume_vacuum_depth_score",
    "trend_proximity_match_score",
]


def aggregate_launchpad_ticker(ticker: TickerResult, regime: MarketRegime) -> TickerResult:
    _ = regime
    raw = sum(
        fr.score for name, fr in ticker.factors.items() if name in LAUNCHPAD_SCORE_FACTORS
    )
    penalty = sum(ticker.penalties.values())
    raw = max(0.0, raw + penalty)
    ticker.raw_score = raw
    ticker.normalized_score = (
        (raw / float(LAUNCHPAD_RAW_SCORE_MAX)) * 100 if LAUNCHPAD_RAW_SCORE_MAX else 0.0
    )
    ticker.regime_multiplier = 1.0
    ticker.final_score = ticker.normalized_score
    return ticker
