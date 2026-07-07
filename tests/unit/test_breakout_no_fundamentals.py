"""Breakout scans should not fetch quarterly fundamentals."""

from __future__ import annotations

from unittest.mock import patch

from quant_hub.engine.context import ScanContext, synthetic_prices
from quant_hub.engine.runner import StrategyEngine
from quant_hub.strategies.breakout.spec import BREAKOUT_STRATEGY


def test_scan_context_skips_fundamentals_when_disabled():
    with patch("quant_hub.engine.context.download_prices") as mock_prices:
        with patch("quant_hub.engine.context.download_fundamentals") as mock_fund:
            mock_prices.return_value = synthetic_prices(["AAPL", "SPY"])
            ctx = ScanContext.from_universe(
                tickers=["AAPL"],
                dry_run=False,
                load_fundamentals=False,
            )
    mock_fund.assert_not_called()
    assert ctx.fund_map == {}
    assert ctx.extras.get("fundamentals_quality") is None


def test_breakout_engine_does_not_load_fundamentals():
    with patch("quant_hub.engine.context.download_prices") as mock_prices:
        with patch("quant_hub.engine.context.download_fundamentals") as mock_fund:
            mock_prices.return_value = synthetic_prices(["AAPL", "SPY", "XLK"])
            engine = StrategyEngine(
                BREAKOUT_STRATEGY,
                tickers=["AAPL"],
                dry_run=False,
            )
            engine.run()
    mock_fund.assert_not_called()
