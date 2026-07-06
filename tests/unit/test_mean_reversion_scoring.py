import pandas as pd

from quant_hub.config import MEAN_REVERSION_HIGH_CONVICTION, MEAN_REVERSION_WATCHLIST
from quant_hub.strategies.mean_reversion.constants import (
    TIER_FILTERED,
    TIER_HIGH_CONVICTION,
    TIER_WATCHLIST,
)
from quant_hub.strategies.mean_reversion.scanner import add_indicators
from quant_hub.strategies.mean_reversion.scoring import score_mean_reversion
from tests.unit.mean_reversion_helpers import synthetic_long_setup_df, synthetic_short_setup_df


def test_score_long_setup_can_reach_high_conviction():
    df = synthetic_long_setup_df()
    enriched = add_indicators(df)
    # Force RSI hook: oversold then cross above 30
    enriched.loc[enriched.index[-4], "RSI"] = 28.0
    enriched.loc[enriched.index[-3], "RSI"] = 27.0
    enriched.loc[enriched.index[-2], "RSI"] = 29.0
    enriched.loc[enriched.index[-1], "RSI"] = 32.0
    result = score_mean_reversion(enriched, rs_percentile=0.75)
    assert result.scored_side == "long"
    assert result.total_score >= MEAN_REVERSION_WATCHLIST
    assert result.long_score >= result.short_score


def test_score_short_side_wins_on_upper_band():
    df = synthetic_short_setup_df()
    enriched = add_indicators(df)
    enriched.loc[enriched.index[-4], "RSI"] = 72.0
    enriched.loc[enriched.index[-3], "RSI"] = 74.0
    enriched.loc[enriched.index[-2], "RSI"] = 71.0
    enriched.loc[enriched.index[-1], "RSI"] = 68.0
    result = score_mean_reversion(enriched, rs_percentile=0.20)
    assert result.scored_side == "short"
    assert result.short_score >= result.long_score


def test_tier_thresholds():
    df = synthetic_long_setup_df()
    enriched = add_indicators(df)
    result = score_mean_reversion(enriched, rs_percentile=0.5)
    if result.total_score > MEAN_REVERSION_HIGH_CONVICTION:
        assert result.tier == TIER_HIGH_CONVICTION
    elif result.total_score >= MEAN_REVERSION_WATCHLIST:
        assert result.tier == TIER_WATCHLIST
    else:
        assert result.tier == TIER_FILTERED


def test_both_sides_scored():
    df = synthetic_long_setup_df()
    enriched = add_indicators(df)
    result = score_mean_reversion(enriched, rs_percentile=0.5)
    assert result.long_score >= 0
    assert result.short_score >= 0
    assert len(result.rule_breakdown) == 6
    assert result.scored_side in ("long", "short")
