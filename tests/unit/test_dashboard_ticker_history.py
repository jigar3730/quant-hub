from __future__ import annotations

from quant_hub.history.ticker_projection import history_display_columns


def test_history_display_columns_launchpad():
    rows = [{"strategy_id": "launchpad"}]
    cols = history_display_columns(rows)
    assert "normalized_score" in cols
    assert "squeeze_intensity" in cols
