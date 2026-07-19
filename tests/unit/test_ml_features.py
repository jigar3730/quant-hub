"""Unit tests for ML feature flattening."""

from __future__ import annotations

from datetime import UTC, date, datetime

from quant_hub.ml.constants import FEATURE_SCHEMA_VERSION
from quant_hub.ml.features import extract_features, merge_outcome_columns


def _run(strategy_id: str = "breakout") -> dict:
    return {
        "id": 42,
        "scan_date": date(2026, 6, 1),
        "scan_time": datetime(2026, 6, 1, 17, 0, tzinfo=UTC),
        "strategy_id": strategy_id,
        "universe_id": "sp500_index",
        "universe_size": 193,
        "regime_label": "neutral",
        "regime_multiplier": 0.85,
        "metadata": {
            "data_provenance": {
                "as_of_price": "2026-05-30",
                "price_cache": True,
                "fundamentals_cache": True,
            }
        },
    }


def test_extract_breakout_features():
    detail = {
        "ticker": "AAPL",
        "tier": "Tier 1",
        "eligible": True,
        "sector_etf": "XLK",
        "summary": {"final_adjusted_score": 88, "normalized_score": 75, "raw_score": 90},
        "scores": {
            "rs_market": {"score": 8},
            "compression": {"score": 7},
        },
    }
    row = extract_features(strategy_id="breakout", detail=detail, run=_run())
    assert row["feature_schema_version"] == FEATURE_SCHEMA_VERSION
    assert row["ticker"] == "AAPL"
    assert row["final_score"] == 88
    assert row["score_rs_market"] == 8
    assert row["as_of_price"] == "2026-05-30"


def test_extract_swing_features():
    detail = {
        "ticker": "MSFT",
        "tier": "SETUP_LONG",
        "eligible": True,
        "setup_detail": {
            "swing_score": 92,
            "quality_label": "high",
            "checks_passed": 5,
            "checks_total": 5,
            "rsi": 48.5,
        },
        "summary": {},
    }
    row = extract_features(strategy_id="swing", detail=detail, run=_run("swing"))
    assert row["swing_score"] == 92
    assert row["quality_label"] == "high"
    assert row["rsi"] == 48.5


def test_extract_lynch_features():
    detail = {
        "ticker": "NVDA",
        "lynch_score": 85,
        "passed": True,
        "peg_ratio": 1.2,
        "categories": ["fast_grower", "stalwart"],
        "metrics": {"eps_growth_5y": 25.0, "data_quality": {"complete": True}},
    }
    row = extract_features(strategy_id="lynch", detail=detail, run=_run("lynch"))
    assert row["lynch_score"] == 85
    assert row["categories"] == "fast_grower,stalwart"
    assert row["fetch_complete"] is True


def test_extract_launchpad_features():
    detail = {
        "ticker": "HOOD",
        "tier": "Tier 2",
        "eligible": True,
        "summary": {
            "final_adjusted_score": 82,
            "normalized_score": 82,
            "raw_score": 82,
        },
        "scores": {
            "squeeze_intensity": {
                "score": 40.0,
                "raw": {"squeeze_ratio": 0.8459, "squeeze_active": True},
            },
            "tightness_percentile": {
                "score": 15.0,
                "raw": {"tightness_rank_pct": 0.0667},
            },
            "volume_vacuum_depth": {
                "score": 15.0,
                "raw": {"rvol": 0.42},
            },
            "trend_proximity_match": {
                "score": 12.0,
                "raw": {"pct_distance": 0.031},
            },
            "macd_zero_line": {"score": 0.0, "raw": {}},
        },
    }
    row = extract_features(strategy_id="launchpad", detail=detail, run=_run("launchpad"))
    assert row["final_score"] == 82
    assert row["volatility_compression_ratio"] == 0.8459
    assert row["relative_strength_rank"] == 0.0667
    assert row["volume_rs_score"] == 0.42
    assert row["resistance_distance_pct"] == 0.031
    assert row["market_regime_multiplier"] == 0.85
    assert row["eligible"] == 1.0
    # Diagnostic score columns still exported
    assert row["score_squeeze_intensity"] == 40.0


def test_merge_outcome_columns():
    features = {"ticker": "AAPL", "final_score": 80}
    outcome = {
        "horizon_days": 10,
        "anchor_date": date(2026, 5, 30),
        "forward_return_pct": 3.5,
        "label_binary": True,
        "label_status": "ok",
    }
    merged = merge_outcome_columns(features, outcome)
    assert merged["forward_return_pct"] == 3.5
    assert merged["label_binary"] is True
    assert merged["ticker"] == "AAPL"
