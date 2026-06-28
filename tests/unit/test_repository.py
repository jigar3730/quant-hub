from __future__ import annotations

import os
from datetime import date, datetime, timezone

import pytest

from quant_hub.infrastructure.postgres.connection import apply_schema, ping
from quant_hub.infrastructure.postgres.repository import ScanRepository


def _postgres_available() -> bool:
    try:
        return ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_available(), reason="Postgres not available")


@pytest.fixture(scope="module", autouse=True)
def _schema():
    apply_schema()


def _sample_report(n: int = 5) -> dict:
    tickers = []
    for i in range(n):
        tickers.append(
            {
                "ticker": f"T{i}",
                "eligible": i % 2 == 0,
                "tier": "Tier 1" if i == 0 else "filtered",
                "sector_etf": "XLK",
                "eligibility": {"fail_reason": None if i % 2 == 0 else "low_volume"},
                "summary": {"final_adjusted_score": 80 - i, "normalized_score": 70, "raw_score": 60},
                "scores": {},
            }
        )
    return {
        "strategy_id": "breakout",
        "scan_summary": {
            "universe_size": n,
            "eligible_count": 3,
            "excluded_count": 2,
            "tier_counts": {"Tier 1": 1, "Tier 2": 0, "Tier 3": 0, "filtered": n - 1},
            "actionable_count": 1,
            "filter_breakdown": {"low_volume": 2},
        },
        "market_regime": {
            "label": "neutral",
            "multiplier": 0.85,
            "spy_price": 500.0,
            "return_63d_pct": 5.0,
            "sma50": 495.0,
            "sma200": 480.0,
            "meaning": "Test regime",
            "high_52w": 510.0,
            "pct_below_52w_high": 2.0,
        },
        "tickers": tickers,
    }


def test_upsert_same_day_replaces_ticker_rows():
    repo = ScanRepository()
    scan_date = date(2099, 1, 1)
    strategy = "breakout"
    universe = "test-upsert"

    for i in range(3):
        report = _sample_report(n=5 + i)
        repo.upsert_scan(
            scan_date=scan_date,
            strategy_id=strategy,
            universe_id=universe,
            report=report,
            scan_time=datetime(2099, 1, 1, 12, i, 0, tzinfo=timezone.utc),
        )

    counts = repo.table_counts()
    loaded = repo.load_report(strategy_id=strategy, universe_id=universe, scan_date=scan_date)
    assert loaded is not None
    assert len(loaded["tickers"]) == 7  # last run had n=7
    assert counts["scan_runs"] >= 1

    runs = [r for r in repo.list_runs(exclude_fixtures=False) if r["universe_id"] == universe and r["scan_date"] == scan_date]
    assert len(runs) == 1


def test_market_regime_roundtrip():
    repo = ScanRepository()
    report = _sample_report()
    repo.upsert_scan(
        scan_date=date(2099, 1, 2),
        strategy_id="breakout",
        universe_id="test-regime-roundtrip",
        report=report,
    )
    loaded = repo.load_report(
        strategy_id="breakout",
        universe_id="test-regime-roundtrip",
        scan_date=date(2099, 1, 2),
        exclude_fixtures=False,
    )
    assert loaded is not None
    regime = loaded["market_regime"]
    assert regime["sma50"] == 495.0
    assert regime["meaning"] == "Test regime"
    repo.delete_fixture_runs()
