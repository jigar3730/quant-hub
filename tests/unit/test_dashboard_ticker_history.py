from __future__ import annotations

from quant_hub.history.ticker_projection import history_display_columns


def test_history_display_columns_mean_reversion():
    rows = [{"strategy_id": "mean_reversion"}]
    cols = history_display_columns(rows)
    assert "mean_reversion_score" in cols
    assert "entry_trigger" in cols
