import time
from pathlib import Path

import pandas as pd

from quant_hub.infrastructure.cache.parquet_cache import ParquetCache


def test_fresh_vs_stale_ttl(tmp_path: Path):
    cache = ParquetCache(base_dir=tmp_path / "prices", ttl_hours=24)
    df = pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=5),
            "Open": [1, 2, 3, 4, 5],
            "High": [1, 2, 3, 4, 5],
            "Low": [1, 2, 3, 4, 5],
            "Close": [1, 2, 3, 4, 5],
            "Volume": [100] * 5,
        }
    )
    cache.write("AAA", df)
    assert cache.is_fresh("AAA")

    path = cache.path_for("AAA")
    old = time.time() - 25 * 3600
    import os

    os.utime(path, (old, old))
    assert not cache.is_fresh("AAA")

    cached, stale = cache.partition(["AAA", "BBB"], use_cache=True)
    assert "BBB" in stale
    assert "AAA" in stale
