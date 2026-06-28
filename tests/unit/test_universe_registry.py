from pathlib import Path

import pytest

from quant_hub.universes.registry import UniverseRegistry


def test_resolve_sp500():
    reg = UniverseRegistry()
    tickers = reg._resolve_id("sp500")
    assert len(tickers) >= 100
    assert "NVDA" in tickers or "AAPL" in tickers


def test_unknown_universe_raises():
    reg = UniverseRegistry()
    with pytest.raises(ValueError, match="Unknown universe"):
        reg._resolve_id("does-not-exist")
