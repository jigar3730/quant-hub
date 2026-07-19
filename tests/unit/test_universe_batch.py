"""Tests for batch universe listing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_hub.universes.batch import list_universe_ids
from quant_hub.universes.registry import UniverseRegistry


def _write_config(tmp_path: Path, universes: dict) -> Path:
    path = tmp_path / "universes.json"
    path.write_text(json.dumps({"universes": universes}))
    return path


def test_list_all_universe_ids_sorted(tmp_path: Path):
    config = _write_config(
        tmp_path,
        {
            "z_last": {"name": "Z", "sources": [{"type": "file", "path": "z.txt"}]},
            "a_first": {"name": "A", "sources": [{"type": "file", "path": "a.txt"}]},
        },
    )
    reg = UniverseRegistry(config_path=config)
    assert list_universe_ids(reg) == ["a_first", "z_last"]


def test_list_lynch_skips_disabled(tmp_path: Path):
    config = _write_config(
        tmp_path,
        {
            "sp500_index": {"name": "Index", "sources": [{"type": "file", "path": "s.txt"}]},
            "etf_only": {
                "name": "ETFs",
                "lynch_enabled": False,
                "eligibility_mode": "etf",
                "sources": [{"type": "file", "path": "e.txt"}],
            },
        },
    )
    reg = UniverseRegistry(config_path=config)
    assert list_universe_ids(reg, strategy="lynch") == ["sp500_index"]


def test_list_launchpad_skips_etf_mode(tmp_path: Path):
    config = _write_config(
        tmp_path,
        {
            "sp500_index": {"name": "Index", "sources": [{"type": "file", "path": "s.txt"}]},
            "etf_only": {
                "name": "ETFs",
                "eligibility_mode": "etf",
                "sources": [{"type": "file", "path": "e.txt"}],
            },
        },
    )
    reg = UniverseRegistry(config_path=config)
    assert list_universe_ids(reg, strategy="launchpad") == ["sp500_index"]


def test_list_explicit_unknown_raises(tmp_path: Path):
    config = _write_config(
        tmp_path,
        {"sp500_index": {"name": "Index", "sources": [{"type": "file", "path": "s.txt"}]}},
    )
    reg = UniverseRegistry(config_path=config)
    with pytest.raises(ValueError, match="Unknown universe"):
        list_universe_ids(reg, explicit=["missing"])


def test_repo_lynch_includes_sp500():
    reg = UniverseRegistry()
    assert reg.is_lynch_enabled("sp500_index") is True
    lynch_ids = list_universe_ids(reg, strategy="lynch")
    assert "sp500_index" in lynch_ids
    assert "mega_runners" in lynch_ids
