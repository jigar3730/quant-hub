"""Tests for actionable signal summaries."""

from quant_hub.dashboard.viz.signals import (
    component_action,
    holding_back_summary,
    rank_components,
    top_signals_short,
    top_signals_tooltip,
)

WST_SCORES = {
    "rs_market": {"score": 15.38, "max": 20, "meaning": "Strong outperformance vs SPY"},
    "rs_sector": {"score": 15.0, "max": 15, "meaning": "Leading XLV sector peers"},
    "accumulation": {"score": 9.23, "max": 12, "meaning": "Heavy volume on up days"},
    "resistance": {"score": 5.0, "max": 5, "meaning": "Within 3% of resistance"},
    "relative_volume": {"score": 5.0, "max": 8, "meaning": "Elevated volume"},
    "pattern": {"score": 4.0, "max": 5, "meaning": "4/5 pattern quality signals met"},
    "compression": {"score": 0.0, "max": 15, "meaning": "Wide Bollinger bands; not compressed"},
}

WST_TICKER = {
    "ticker": "WST",
    "tier": "Tier 3",
    "tier_reason": "Below watchlist threshold: normalized score 63.8 (<60)",
    "summary": {"normalized_score": 63.85, "final_adjusted_score": 54.27},
    "scores": WST_SCORES,
}


def test_wst_top_signals_rank_by_pct_not_raw_points():
    short = top_signals_short(WST_SCORES)
    assert short.startswith("RS vs Sector 15/15✓")
    assert "Resistance 5/5✓" in short
    assert "Pattern 4/5" in short


def test_wst_compression_actionable_gap():
    action = component_action("compression", WST_SCORES["compression"])
    assert "squeeze" in action.lower() or "wide" in action.lower()


def test_wst_holding_back_mentions_norm_and_compression():
    text = holding_back_summary(WST_TICKER)
    assert "60" in text or "watchlist" in text.lower()
    assert "squeeze" in text.lower() or "wide" in text.lower()


def test_top_signals_tooltip_is_multiline_actionable():
    tip = top_signals_tooltip(WST_SCORES, n=2)
    assert "•" in tip
    assert len(tip.splitlines()) >= 2


def test_rank_components_returns_actions():
    ranked = rank_components(WST_SCORES, n=3)
    assert ranked[0].pct >= ranked[-1].pct
    assert all(r.action for r in ranked)
