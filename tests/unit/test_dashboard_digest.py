"""Tests for dashboard digest preview."""

from __future__ import annotations

from datetime import date

from quant_hub.dashboard.viz.digest_components import build_digest_preview, digest_job_name
from quant_hub.digest import policy as P


def _launchpad_ticker(ticker: str, tier: str, score: float) -> dict:
    return {
        "ticker": ticker,
        "tier": tier,
        "sector_etf": "XLK",
        "tier_reason": "Squeeze and volume vacuum confirm.",
        "summary": {"final_adjusted_score": score, "normalized_score": score},
        "scores": {"squeeze_intensity": {"score": 9, "max": 40}},
    }


class _FakeRepo:
    def __init__(self, report: dict, *, scan_date: date) -> None:
        self._report = report
        self._scan_date = scan_date
        self._runs = [{"id": 1, "scan_date": scan_date, "universe_id": P.DAILY_LAUNCHPAD_UNIVERSE}]

    def load_report(self, **kwargs):
        if kwargs.get("scan_date") == self._scan_date:
            return self._report
        return None

    def list_runs(self, **kwargs):
        return self._runs

    def get_latest_run(self, **kwargs):
        if kwargs.get("universe_id") == P.DAILY_LAUNCHPAD_UNIVERSE:
            return {"id": 1, "scan_date": self._scan_date}
        return None

    def list_ticker_details_for_run(self, run_id: int):
        assert run_id == 1
        return self._report["tickers"]

    def list_runs_filtered(self, **kwargs):
        return []


def test_digest_job_name():
    assert digest_job_name("daily", date(2026, 7, 1)) == "digest-daily-2026-07-01"
    assert digest_job_name("weekly", date(2026, 7, 1)) == "digest-weekly-2026-07-01"


def test_build_digest_preview_daily():
    report = {
        "market_regime": {"label": "strong", "multiplier": 1.0, "spy_price": 550},
        "scan_summary": {"universe_size": 3},
        "tickers": [_launchpad_ticker("AAA", "Tier 1", 88.0)],
    }
    repo = _FakeRepo(report, scan_date=date(2026, 7, 1))
    preview = build_digest_preview(repo, digest_kind="daily", scan_date=date(2026, 7, 1))
    assert "AAA" in preview["html"]
    assert preview["payload"]["tier1"][0]["ticker"] == "AAA"
    assert "brief" in preview["subject"].lower() or "AAA" in preview["subject"]
