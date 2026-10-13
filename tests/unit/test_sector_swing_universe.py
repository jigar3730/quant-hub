"""The sector_etfs universe must not leak into existing Launchpad/Lynch batch jobs."""

from __future__ import annotations

from quant_hub.config import ALL_SECTOR_ETFS
from quant_hub.universes.batch import list_universe_ids
from quant_hub.universes.registry import UniverseRegistry


def test_sector_etfs_universe_covers_repo_etf_set():
    # Extra ETFs may be added to the file; the repo's sector/industry set must stay in it.
    reg = UniverseRegistry()
    _, tickers = reg.resolve("sector_etfs")
    assert set(ALL_SECTOR_ETFS) <= set(tickers)
    assert len(tickers) == len(set(tickers))
    assert "SPY" not in tickers
    assert reg.get_eligibility_mode("sector_etfs") == "etf"
    assert reg.is_lynch_enabled("sector_etfs") is False


def test_sector_etfs_excluded_from_launchpad_and_lynch_batches():
    reg = UniverseRegistry()
    assert "sector_etfs" in list_universe_ids(reg)  # visible for --universe lookups
    assert "sector_etfs" not in list_universe_ids(reg, strategy="launchpad")
    assert "sector_etfs" not in list_universe_ids(reg, strategy="lynch")


def test_existing_batch_universe_lists_unchanged(tmp_path):
    """Batch lists with sector_etfs present equal the lists for the same config without it."""
    import json

    from quant_hub.config import UNIVERSES_CONFIG

    config = json.loads(UNIVERSES_CONFIG.read_text())
    del config["universes"]["sector_etfs"]
    without = tmp_path / "universes.json"
    without.write_text(json.dumps(config))

    with_reg, without_reg = UniverseRegistry(), UniverseRegistry(config_path=without)
    for strategy in ("launchpad", "lynch"):
        assert list_universe_ids(with_reg, strategy=strategy) == list_universe_ids(
            without_reg, strategy=strategy
        )
    assert "sp500_index" in list_universe_ids(with_reg, strategy="launchpad")


def test_launchpad_daily_skips_sector_etfs(monkeypatch):
    from quant_hub.cli import launchpad_daily

    monkeypatch.setattr(launchpad_daily, "setup_logging", lambda *_: None)
    # ETF-mode universes return 0 before any scan/DB work happens.
    assert launchpad_daily.run_daily_scan(universe_id="sector_etfs", dry_run=True) == 0
