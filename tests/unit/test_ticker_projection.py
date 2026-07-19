from __future__ import annotations

from datetime import date

from quant_hub.history.ticker_projection import history_display_columns, project_row


def test_project_launchpad_row():
    detail = {
        "tier_reason": "Strong squeeze",
        "summary": {"normalized_score": 72.0, "final_adjusted_score": 68.5},
        "scores": {
            "macd_zero_line": {"score": 12},
            "squeeze_intensity": {"score": 9},
            "tightness_percentile": {"score": 8},
        },
    }
    row = project_row(
        run_id=1,
        scan_date=date(2024, 6, 1),
        scan_time=None,
        strategy_id="launchpad",
        universe_id="sp500_index",
        regime_label="strong",
        regime_multiplier=1.0,
        ticker="NVDA",
        eligible=True,
        tier="Tier 1",
        sector_etf="XLK",
        final_score=68.5,
        filter_reason=None,
        detail=detail,
    )
    assert row["normalized_score"] == 72.0
    assert row["squeeze_intensity"] == 9.0
    assert row["strategy_label"] == "Launchpad"


def test_project_lynch_row_includes_institutional():
    detail = {
        "passed": True,
        "lynch_score": 85,
        "categories": ["fast_grower"],
        "institutional_pct": 42.5,
        "analyst_count": 5,
        "peg_ratio": 0.9,
        "pe_ratio": 18.0,
        "metrics": {},
    }
    row = project_row(
        run_id=2,
        scan_date=date(2024, 6, 8),
        scan_time=None,
        strategy_id="lynch",
        universe_id="sp500_index",
        regime_label=None,
        regime_multiplier=None,
        ticker="NVDA",
        eligible=True,
        tier="fast_grower",
        sector_etf=None,
        final_score=85.0,
        filter_reason=None,
        detail=detail,
    )
    assert row["institutional_pct"] == 42.5
    assert row["analyst_count"] == 5
    assert row["categories"] == "fast_grower"


def test_history_display_columns_includes_lynch_fields():
    rows = [
        {"strategy_id": "launchpad"},
        {"strategy_id": "lynch"},
    ]
    cols = history_display_columns(rows)
    assert "institutional_pct" in cols
    assert "scan_date" in cols
