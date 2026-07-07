"""Launchpad scan service smoke test."""

from quant_hub.application.scan_service import ScanService
from quant_hub.universes.batch import list_universe_ids
from quant_hub.universes.registry import UniverseRegistry


def test_launchpad_dry_run_scan():
    service = ScanService(strategy_id="launchpad")
    result = service.run(
        tickers=["AAA", "BBB"],
        dry_run=True,
        report=None,
        persist=False,
    )
    assert result.ok
    assert not result.dataframe.empty
    assert "tier" in result.dataframe.columns


def test_launchpad_batch_excludes_etf_universes():
    reg = UniverseRegistry()
    ids = list_universe_ids(reg, strategy="launchpad")
    etf_ids = [uid for uid in reg.list_universes() if reg.get_eligibility_mode(uid) == "etf"]
    assert etf_ids, "expected at least one ETF-mode universe in config"
    for etf_id in etf_ids:
        assert etf_id not in ids
    # Stock-mode universes remain included.
    assert any(reg.get_eligibility_mode(uid) == "stock" for uid in ids)


def test_launchpad_daily_skips_etf_universe():
    from quant_hub.cli.launchpad_daily import run_daily_scan

    reg = UniverseRegistry()
    etf_ids = [uid for uid in reg.list_universes() if reg.get_eligibility_mode(uid) == "etf"]
    assert etf_ids
    # ETF-mode universe should be skipped cleanly (exit 0) without touching the DB.
    rc = run_daily_scan(universe_id=etf_ids[0], send_email=False, use_cache=False)
    assert rc == 0
