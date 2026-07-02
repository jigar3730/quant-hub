"""CLI and service default universe arguments."""

import inspect

from quant_hub.application.lynch_service import LynchScanService
from quant_hub.application.ml_cache_service import MLCacheService
from quant_hub.application.swing_service import SwingScanService
from quant_hub.cli import backfill, daily, swing
from quant_hub.config import PRIMARY_INDEX_UNIVERSE
from quant_hub.lynch.runner import LynchScannerRunner


def test_daily_run_default_universe():
    sig = inspect.signature(daily.run_daily_scan)
    assert sig.parameters["universe_id"].default == PRIMARY_INDEX_UNIVERSE


def test_swing_run_default_universe():
    sig = inspect.signature(swing.run_swing_scan)
    assert sig.parameters["universe_id"].default == PRIMARY_INDEX_UNIVERSE


def test_swing_service_default_universe():
    sig = inspect.signature(SwingScanService.run)
    assert sig.parameters["universe_id"].default == PRIMARY_INDEX_UNIVERSE


def test_lynch_service_default_universe():
    sig = inspect.signature(LynchScanService.run)
    assert sig.parameters["universe_id"].default == PRIMARY_INDEX_UNIVERSE


def test_backfill_range_args_default():
    import argparse

    p = argparse.ArgumentParser()
    backfill._add_range_args(p)
    ns = p.parse_args(["--since", "2024-01-01"])
    assert ns.universe == PRIMARY_INDEX_UNIVERSE


def test_ml_cache_service_default():
    sig = inspect.signature(MLCacheService.warm_daily_prices)
    assert sig.parameters["universe_id"].default == PRIMARY_INDEX_UNIVERSE


def test_lynch_runner_default():
    sig = inspect.signature(LynchScannerRunner.__init__)
    assert sig.parameters["universe_id"].default == PRIMARY_INDEX_UNIVERSE
