from quant_hub.config import MEAN_REVERSION_HIGH_CONVICTION
from quant_hub.strategies.mean_reversion.constants import TIER_FILTERED, TIER_HIGH_CONVICTION
from quant_hub.strategies.mean_reversion.scanner import analyze_ticker, analysis_to_report
from quant_hub.strategies.mean_reversion.scoring import MeanReversionScoreResult
from quant_hub.strategies.mean_reversion.trade_plan import build_trade_card
from tests.unit.mean_reversion_helpers import (
    synthetic_daily_bars,
    synthetic_long_setup_df,
)


def test_trade_plan_long_rr_and_levels():
    df = synthetic_long_setup_df()
    analysis = analyze_ticker(df, "XLV", rs_percentile=0.8, min_bars=520)
    assert analysis.score_result is not None
    score = analysis.score_result
    if score.tier != TIER_HIGH_CONVICTION:
        score = MeanReversionScoreResult(
            total_score=75.0,
            scored_side="long",
            setup_type="SETUP_LONG",
            signal="Strong Long",
            tier=TIER_HIGH_CONVICTION,
            rule_breakdown=score.rule_breakdown,
            long_score=75.0,
            short_score=score.short_score,
        )
    plan = build_trade_card(analysis, score, df)
    assert plan["stop_loss"] < plan["current_price"]
    assert plan["target_1_bb_mean"] > plan["current_price"]
    assert plan["target_2_opposite_band"] >= plan["target_1_bb_mean"]
    assert plan["options_type"] == "Bull Call Debit Spread"
    assert ": 1" in plan["rr_t1"]
    assert ": 1" in plan["rr_t2"]


def test_trade_plan_qqq_delta():
    df = synthetic_long_setup_df()
    analysis = analyze_ticker(df, "QQQ", rs_percentile=0.9, min_bars=520)
    score = MeanReversionScoreResult(
        total_score=75.0,
        scored_side="long",
        setup_type="SETUP_LONG",
        signal="Strong Long",
        tier=TIER_HIGH_CONVICTION,
        rule_breakdown=[],
        long_score=75.0,
        short_score=20.0,
    )
    plan = build_trade_card(analysis, score, df)
    assert plan["suggested_delta"] == "0.65 – 0.80"


def test_analysis_to_report_includes_trade_plan_when_high_conviction():
    df = synthetic_long_setup_df()
    analysis = analyze_ticker(df, "TEST", rs_percentile=0.85, min_bars=520)
    if analysis.score_result and analysis.score_result.total_score <= MEAN_REVERSION_HIGH_CONVICTION:
        analysis.score_result = MeanReversionScoreResult(
            total_score=74.0,
            scored_side="long",
            setup_type="SETUP_LONG",
            signal="Strong Long",
            tier=TIER_HIGH_CONVICTION,
            rule_breakdown=analysis.score_result.rule_breakdown,
            long_score=74.0,
            short_score=analysis.score_result.short_score,
        )
    report = analysis_to_report(analysis, df)
    assert report["setup_detail"]["rule_breakdown"]
    assert "trade_plan" in report["setup_detail"]
    assert report["tier"] == TIER_HIGH_CONVICTION


def test_analysis_to_report_no_trade_plan_when_filtered():
    df = synthetic_long_setup_df()
    analysis = analyze_ticker(df, "TEST", rs_percentile=0.5, min_bars=520)
    analysis.score_result = MeanReversionScoreResult(
        total_score=55.0,
        scored_side="long",
        setup_type="SETUP_LONG",
        signal="No Trade",
        tier=TIER_FILTERED,
        rule_breakdown=[],
        long_score=55.0,
        short_score=40.0,
    )
    report = analysis_to_report(analysis, df)
    assert "trade_plan" not in report["setup_detail"]


def test_insufficient_bars_filtered():
    df = synthetic_daily_bars(100)
    analysis = analyze_ticker(df, "TEST", min_bars=520)
    assert analysis.fail_reason == "insufficient_data"
    report = analysis_to_report(analysis, df)
    assert report["tier"] == TIER_FILTERED
