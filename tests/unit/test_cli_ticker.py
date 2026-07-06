from __future__ import annotations

import json
from io import StringIO
from unittest.mock import MagicMock, patch

from quant_hub.cli.status import main


def test_ticker_history_json_output():
    repo = MagicMock()
    repo.ticker_history_count.return_value = 1
    repo.ticker_history.return_value = [
        {
            "scan_date": "2024-06-01",
            "strategy_id": "breakout",
            "strategy_label": "Breakout",
            "universe_id": "sp500_index",
            "ticker": "NVDA",
            "tier_label": "High conv.",
            "final_score": 75.0,
        }
    ]
    with patch("quant_hub.cli.status.ping", return_value=True), patch(
        "quant_hub.cli.status.ScanRepository", return_value=repo
    ):
        captured = StringIO()
        with patch("sys.stdout", captured):
            code = main(["ticker", "history", "NVDA", "--json"])
    assert code == 0
    payload = json.loads(captured.getvalue())
    assert payload[0]["ticker"] == "NVDA"
    repo.ticker_history.assert_called_once()


def test_ticker_show_missing_report():
    repo = MagicMock()
    repo.load_report.return_value = None
    with patch("quant_hub.cli.status.ping", return_value=True), patch(
        "quant_hub.cli.status.ScanRepository", return_value=repo
    ):
        code = main(
            [
                "ticker",
                "show",
                "NVDA",
                "--strategy",
                "lynch",
                "--universe",
                "sp500_index",
            ]
        )
    assert code == 1
