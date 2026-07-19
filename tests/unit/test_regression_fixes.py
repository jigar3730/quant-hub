"""Regression tests for critical QA fixes."""

from quant_hub.application.run_result import ServiceRunResult
from quant_hub.config import DRY_RUN_OUTPUT_DIR, OUTPUT_DIR, scan_output_paths
from quant_hub.engine.runner import StrategyEngine
from quant_hub.strategies.registry import get_strategy


def test_scan_output_paths_per_universe():
    paths = scan_output_paths("launchpad", "sp500_index")
    assert paths["csv"] == OUTPUT_DIR / "launchpad" / "sp500_index" / "scan_results.csv"
    assert paths["json"] == OUTPUT_DIR / "launchpad" / "sp500_index" / "report.json"


def test_dry_run_output_isolated():
    paths = scan_output_paths("launchpad", "custom", dry_run=True)
    assert paths["csv"] == DRY_RUN_OUTPUT_DIR / "launchpad" / "custom" / "scan_results.csv"
    assert not str(paths["csv"]).startswith(str(OUTPUT_DIR / "launchpad"))


def test_service_run_result_email_exit_code():
    ok = ServiceRunResult(dataframe=__import__("pandas").DataFrame(), email_requested=False)
    assert ok.exit_code() == 0

    failed = ServiceRunResult(
        dataframe=__import__("pandas").DataFrame(),
        email_requested=True,
        email_sent=False,
    )
    assert failed.exit_code() == 1


def test_engine_marks_compute_error_ineligible(monkeypatch):
    """One ticker with a failing factor should not abort the full scan."""
    engine = StrategyEngine(get_strategy("launchpad"), tickers=["AAA", "BBB"], dry_run=True)
    for binding in engine.spec.factor_bindings:
        factor = binding.factor
        if factor.pass_kind != "ticker":
            continue
        original = factor.compute

        def make_wrapper(orig):
            def wrapper(ctx, ticker):
                if ticker == "BBB":
                    raise RuntimeError("synthetic factor failure")
                return orig(ctx, ticker)

            return wrapper

        monkeypatch.setattr(factor, "compute", make_wrapper(original))

    result = engine.run()
    by_ticker = {t.ticker: t for t in result.tickers}
    assert "AAA" in by_ticker
    assert "BBB" in by_ticker
    assert by_ticker["BBB"].eligible is False
    assert by_ticker["BBB"].filter_reason in {
        "compute_error",
        "no_price_data",
        "insufficient_history",
    } or by_ticker["BBB"].filter_reason
