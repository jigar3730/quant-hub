"""Regression tests for critical QA fixes."""

import pytest

from quant_hub.application.run_result import ServiceRunResult
from quant_hub.application.swing_service import _data_error_report, build_swing_report
from quant_hub.config import DRY_RUN_OUTPUT_DIR, OUTPUT_DIR, scan_output_paths
from quant_hub.engine.runner import StrategyEngine
from quant_hub.engine.types import TickerResult
from quant_hub.strategies.registry import get_strategy
from quant_hub.strategies.swing.scanner import SwingSetup


def test_scan_output_paths_per_universe():
    paths = scan_output_paths("breakout", "sp500")
    assert paths["csv"] == OUTPUT_DIR / "breakout" / "sp500" / "scan_results.csv"
    assert paths["json"] == OUTPUT_DIR / "breakout" / "sp500" / "report.json"


def test_dry_run_output_isolated():
    paths = scan_output_paths("breakout", "custom", dry_run=True)
    assert paths["csv"] == DRY_RUN_OUTPUT_DIR / "breakout" / "custom" / "scan_results.csv"
    assert not str(paths["csv"]).startswith(str(OUTPUT_DIR / "breakout"))


def test_service_run_result_email_exit_code():
    ok = ServiceRunResult(dataframe=__import__("pandas").DataFrame(), email_requested=False)
    assert ok.exit_code() == 0

    failed = ServiceRunResult(
        dataframe=__import__("pandas").DataFrame(),
        email_requested=True,
        email_sent=False,
    )
    assert failed.exit_code() == 1


def test_swing_report_includes_full_universe():
    setups = [
        SwingSetup(
            ticker="AAA",
            setup_type="SETUP_LONG",
            close=100.0,
            ema20=98.0,
            ema50=95.0,
            rsi=55.0,
            atr=2.0,
            notes="test",
        )
    ]
    tickers_report = [
        {
            "ticker": "AAA",
            "eligible": True,
            "tier": "SETUP_LONG",
            "eligibility": {"passed": True, "fail_reason": None, "checks": []},
        },
        {
            "ticker": "BBB",
            "eligible": False,
            "tier": "filtered",
            "eligibility": {"passed": False, "fail_reason": "no_setup", "checks": []},
        },
        _data_error_report("CCC", "insufficient_data"),
    ]
    report = build_swing_report(
        universe=["AAA", "BBB", "CCC"],
        tickers_report=tickers_report,
        setups=setups,
        rejection_counts={"no_setup": 1, "insufficient_data": 1},
    )
    assert len(report["tickers"]) == 3
    by_ticker = {t["ticker"]: t for t in report["tickers"]}
    assert by_ticker["AAA"]["eligible"] is True
    assert by_ticker["BBB"]["eligible"] is False
    assert by_ticker["CCC"]["eligibility"]["fail_reason"] == "insufficient_data"


def test_engine_marks_compute_error_ineligible(monkeypatch):
    """One ticker with a failing factor should not abort the full scan."""
    engine = StrategyEngine(get_strategy("breakout"), tickers=["AAA", "BBB"], dry_run=True)
    for binding in engine.spec.factor_bindings:
        factor = binding.factor
        if factor.pass_kind != "ticker":
            continue
        original = factor.compute

        def make_wrapper(orig):
            def wrapper(ctx, ticker):
                if ticker == "BBB":
                    raise RuntimeError("simulated factor failure")
                return orig(ctx, ticker)

            return wrapper

        monkeypatch.setattr(factor, "compute", make_wrapper(original))

    result = engine.run()
    by_ticker = {t.ticker: t for t in result.tickers}
    assert by_ticker["BBB"].eligible is False
    assert by_ticker["BBB"].filter_reason == "compute_error"
    assert len(result.tickers) == 2


def test_dashboard_import_smoke():
    pytest.importorskip("streamlit")
    from quant_hub.dashboard import app  # noqa: F401
    from quant_hub.data.news import fetch_ticker_news, fetch_ticker_snapshot  # noqa: F401

    assert callable(fetch_ticker_news)
    assert callable(fetch_ticker_snapshot)
