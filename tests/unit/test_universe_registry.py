from quant_hub.universes.registry import UniverseRegistry


def test_resolve_sp500_index():
    reg = UniverseRegistry()
    tickers = reg._resolve_id("sp500_index")
    assert len(tickers) >= 400
    assert "NVDA" in tickers or "AAPL" in tickers


def test_sp500_removed_raises():
    reg = UniverseRegistry()
    try:
        reg._resolve_id("sp500")
        raise AssertionError("expected ValueError for removed sp500 universe")
    except ValueError as exc:
        assert "Unknown universe" in str(exc)


def test_sp500_index_configured():
    reg = UniverseRegistry()
    assert reg.get_refresh_config("sp500_index") == {"provider": "ssga_spy"}
    path = reg.get_file_source_path("sp500_index")
    assert path is not None
    assert path.name == "sp500_index.txt"


def test_unknown_universe_raises():
    reg = UniverseRegistry()
    try:
        reg._resolve_id("does-not-exist")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "Unknown universe" in str(exc)
