from quant_hub.data.fundamentals.cache import FundamentalsCache
from quant_hub.data.fundamentals.types import FundamentalsSnapshot


def test_fundamentals_cache_roundtrip(tmp_path):
    cache = FundamentalsCache(base_dir=tmp_path, ttl_hours=24)
    snap = FundamentalsSnapshot(
        ticker="TEST",
        revenue_yoy=0.12,
        revenue_yoy_status="OK",
        revenue_yoy_source="single_quarter_yoy",
        eps_combined=0.25,
        eps_combined_status="OK",
        eps_source="diluted_eps_ttm",
        quarters_available=8,
    )
    cache.write(snap)
    assert cache.is_fresh("TEST")
    loaded = cache.read("TEST")
    assert loaded is not None
    assert loaded.revenue_yoy == 0.12
    assert loaded.eps_combined_status == "OK"
