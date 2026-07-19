"""Tests for dashboard UX helpers."""

from __future__ import annotations

import pandas as pd

from quant_hub.dashboard.viz.labels import format_report_label, tier_friendly
from quant_hub.dashboard.viz.launchpad_filters import launchpad_scatter_dataframe
from quant_hub.dashboard.viz.navigation import ticker_link_html, yahoo_finance_url
from quant_hub.dashboard.viz.table_helpers import table_column_order, with_yahoo_ticker_links
from quant_hub.dashboard.viz.ux_helpers import near_miss_dataframe


def test_yahoo_finance_url():
    assert yahoo_finance_url("aapl") == "https://finance.yahoo.com/quote/AAPL"


def test_ticker_link_html_external():
    html = ticker_link_html("MSFT")
    assert "finance.yahoo.com/quote/MSFT" in html
    assert 'target="_blank"' in html


def test_with_yahoo_ticker_links():
    df = pd.DataFrame({"ticker": ["AAPL"], "final_score": [80.0]})
    linked = with_yahoo_ticker_links(df)
    assert linked.iloc[0]["ticker_link"] == "https://finance.yahoo.com/quote/AAPL#AAPL"
    assert linked.iloc[0]["ticker"] == "AAPL"


def test_table_column_order():
    assert table_column_order(["ticker", "tier"]) == ["ticker_link", "tier"]


def test_format_report_label():
    assert format_report_label(
        strategy_id="launchpad",
        universe_id="sp500_index",
        scan_date="2026-06-27",
    ) == "SP500 INDEX · Launchpad · 2026-06-27"


def test_tier_friendly():
    assert tier_friendly("Tier 1") == "High conviction"
    assert tier_friendly("fast_grower") == "Fast grower"


def test_near_miss_dataframe_tier3_close_to_threshold():
    df = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "eligible": True,
                "tier": "Tier 3",
                "normalized_score": 62.0,
                "final_score": 55.0,
                "tier_reason": "Below watchlist",
            },
            {
                "ticker": "BBB",
                "eligible": True,
                "tier": "Tier 3",
                "normalized_score": 50.0,
                "final_score": 45.0,
                "tier_reason": "Too low",
            },
        ]
    )
    near = near_miss_dataframe(df)
    assert list(near["ticker"]) == ["AAA"]


def test_near_miss_dataframe_tier2_high_normalized():
    df = pd.DataFrame(
        [
            {
                "ticker": "CCC",
                "eligible": True,
                "tier": "Tier 2",
                "normalized_score": 82.0,
                "final_score": 68.0,
                "tier_reason": "Missing T1 criteria",
            },
        ]
    )
    near = near_miss_dataframe(df)
    assert list(near["ticker"]) == ["CCC"]


def test_launchpad_scatter_dataframe_uses_current_score_keys():
    tickers = [
        {
            "ticker": "AAPL",
            "eligible": True,
            "tier": "Tier 1",
            "scores": {
                "squeeze_intensity": {"score": 87.0},
                "tightness_percentile": {"score": 72.0},
            },
            "summary": {"final_adjusted_score": 80.0},
        }
    ]

    df = launchpad_scatter_dataframe(tickers)

    assert list(df.columns) == [
        "ticker",
        "tier",
        "squeeze_intensity",
        "tightness_percentile",
        "final_score",
        "normalized_score",
    ]
    assert df.iloc[0]["squeeze_intensity"] == 87.0
    assert df.iloc[0]["tightness_percentile"] == 72.0
