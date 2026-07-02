import pytest

from quant_hub.application.scan_service import ScanService
from quant_hub.engine.runner import StrategyEngine
from quant_hub.infrastructure.postgres.connection import apply_schema, ping
from quant_hub.strategies.registry import get_strategy


def _postgres_available() -> bool:
    try:
        return ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="Postgres not available")


@pytest.fixture(scope="module", autouse=True)
def _schema():
    apply_schema()


def test_scan_service_dry_run_persists(tmp_path):
    service = ScanService()
    result = service.run(
        tickers=["AAA", "BBB", "CCC"],
        use_cache=False,
        dry_run=True,
        report="json",
        output=tmp_path / "out.csv",
        report_json=tmp_path / "out.json",
    )
    assert len(result.dataframe) == 3

    report = service.scan_repo.load_report(universe_id="custom", exclude_fixtures=False)
    assert report is not None
    assert len(report["tickers"]) == 3


def test_engine_breakout_parity_dry_run():
    tickers = ["AAA", "BBB", "CCC"]
    engine = StrategyEngine(get_strategy("breakout"), tickers=tickers, dry_run=True)
    engine_df = engine.run().to_dataframe()
    assert len(engine_df) == 3
    assert "final_adjusted_score" in engine_df.columns


def test_scan_service_sp500_index_dry_run_no_legacy_copy(tmp_path):
    import inspect

    from quant_hub.application import scan_service as scan_module

    assert "copy_to_legacy" not in inspect.getsource(scan_module)

    service = ScanService()
    result = service.run(
        tickers=["AAA", "BBB"],
        use_cache=False,
        dry_run=True,
        report="both",
        output=tmp_path / "out.csv",
        report_json=tmp_path / "out.json",
        report_md=tmp_path / "out.md",
        persist=False,
    )
    assert len(result.dataframe) == 2
