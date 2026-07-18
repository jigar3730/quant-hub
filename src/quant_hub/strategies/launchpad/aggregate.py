from __future__ import annotations

from quant_hub.config import LAUNCHPAD_RAW_SCORE_MAX
from quant_hub.engine.types import TickerResult
from quant_hub.regime.market import MarketRegime

LAUNCHPAD_SCORE_COLUMNS = [
    "squeeze_intensity_score",
    "tightness_percentile_score",
    "volume_vacuum_depth_score",
    "trend_proximity_match_score",
]


def aggregate_launchpad_ticker(ticker: TickerResult, regime: MarketRegime) -> TickerResult:
    _ = regime
    raw = sum(fr.score for fr in ticker.factors.values())
    penalty = sum(ticker.penalties.values())
    raw = max(0.0, raw + penalty)
    ticker.raw_score = raw
    ticker.normalized_score = (
        (raw / float(LAUNCHPAD_RAW_SCORE_MAX)) * 100 if LAUNCHPAD_RAW_SCORE_MAX else 0.0
    )
    ticker.regime_multiplier = 1.0
    ticker.final_score = ticker.normalized_score
    return ticker
