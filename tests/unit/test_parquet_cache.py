import os
import time
from pathlib import Path

import pandas as pd

from quant_hub.infrastructure.cache.parquet_cache import ParquetCache


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.date_range("2024-01-01", periods=5),
            "Open": [1, 2, 3, 4, 5],
            "High": [1, 2, 3, 4, 5],
            "Low": [1, 2, 3, 4, 5],
            "Close": [1, 2, 3, 4, 5],
            "Volume": [100] * 5,
        }
    )


def test_fresh_vs_stale_ttl(tmp_path: Path):
    cache = ParquetCache(base_dir=tmp_path / "prices", ttl_hours=24)
    cache.write("AAA", _sample_df())
    assert cache.is_fresh("AAA")

    path = cache.path_for("AAA")
    old = time.time() - 25 * 3600
    os.utime(path, (old, old))
    assert not cache.is_fresh("AAA")

    cached, stale = cache.partition(["AAA", "BBB"], use_cache=True)
    assert "BBB" in stale
    assert "AAA" in stale


def test_partition_use_cache_false_fetches_all(tmp_path: Path):
    cache = ParquetCache(base_dir=tmp_path / "prices", ttl_hours=24)
    cache.write("AAA", _sample_df())
    cached, stale = cache.partition(["AAA", "BBB"], use_cache=False)
    assert cached == []
    assert stale == ["AAA", "BBB"]


def test_write_is_atomic_no_tmp_left(tmp_path: Path):
    cache = ParquetCache(base_dir=tmp_path / "prices", ttl_hours=24)
    cache.write("AAA", _sample_df())
    path = cache.path_for("AAA")
    assert path.exists()
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    read = cache.read("AAA")
    assert read is not None
    assert len(read) == 5
