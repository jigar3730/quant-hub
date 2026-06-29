"""Unit tests for swing backfill point-in-time logic."""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from quant_hub.application.swing_backfill_service import SwingBackfillService


def _weekly_df(fridays: list[str], base: float = 100.0) -> pd.DataFrame:
    closes = [base + i * 0.8 for i in range(len(fridays))]
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(fridays),
            "Open": closes,
            "High": [c + 1 for c in closes],
            "Low": [c - 1 for c in closes],
            "Close": closes,
            "Volume": 1_000_000,
        }
    )


@pytest.fixture
def mock_universe():
    return "sp500", ["AAA", "BBB"]


def test_backfill_persists_one_friday(mock_universe):
    universe_id, tickers = mock_universe
    fridays = pd.date_range("2023-01-06", periods=70, freq="W-FRI").strftime("%Y-%m-%d").tolist()
    price_map = {t: _weekly_df(fridays, 100.0 + i * 10) for i, t in enumerate(["AAA", "BBB", "SPY"])}

    scan_repo = MagicMock()
    scan_repo.list_runs_filtered.return_value = []
    scan_repo.upsert_scan.return_value = 42

    job_repo = MagicMock()
    job_repo.start_job.return_value = 1

    universe_service = MagicMock()
    universe_service.resolve.return_value = (universe_id, tickers)

    service = SwingBackfillService(
        universe_service=universe_service,
        scan_repo=scan_repo,
        job_repo=job_repo,
    )

    with patch(
        "quant_hub.application.swing_backfill_service.download_weekly_prices",
        return_value=price_map,
    ), patch(
        "quant_hub.application.swing_backfill_service.scan_universe_weekly",
        return_value=([], [{"ticker": "AAA", "tier": "filtered"}], {}),
    ):
        stats = service.run(
            universe_id=universe_id,
            since=date(2024, 6, 7),
            until=date(2024, 6, 7),
            resume=False,
            persist=True,
            job_name="test-backfill",
        )

    assert stats.dates_planned == 1
    assert stats.dates_written == 1
    assert stats.dates_failed == 0
    scan_repo.upsert_scan.assert_called_once()
    call_kwargs = scan_repo.upsert_scan.call_args.kwargs
    assert call_kwargs["scan_date"] == date(2024, 6, 7)
    assert call_kwargs["strategy_id"] == "swing"
    prov = call_kwargs["report"]["data_provenance"]
    assert prov["backfill"] is True
    assert prov["backfill_version"] == "v1"


def test_backfill_resume_skips_existing(mock_universe):
    universe_id, tickers = mock_universe
    fridays = pd.date_range("2023-01-06", periods=70, freq="W-FRI").strftime("%Y-%m-%d").tolist()
    price_map = {t: _weekly_df(fridays) for t in ["AAA", "BBB", "SPY"]}

    scan_repo = MagicMock()
    scan_repo.list_runs_filtered.return_value = [{"scan_date": date(2024, 6, 7)}]

    universe_service = MagicMock()
    universe_service.resolve.return_value = (universe_id, tickers)

    service = SwingBackfillService(
        universe_service=universe_service,
        scan_repo=scan_repo,
        job_repo=MagicMock(),
    )

    with patch(
        "quant_hub.application.swing_backfill_service.download_weekly_prices",
        return_value=price_map,
    ), patch(
        "quant_hub.application.swing_backfill_service.scan_universe_weekly",
        return_value=([], [{"ticker": "AAA", "tier": "filtered"}], {}),
    ):
        stats = service.run(
            since=date(2024, 6, 7),
            until=date(2024, 6, 7),
            resume=True,
            persist=True,
            job_name=None,
        )

    assert stats.dates_skipped == 1
    assert stats.dates_written == 0
    scan_repo.upsert_scan.assert_not_called()
