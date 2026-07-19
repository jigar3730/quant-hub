"""Unit tests for Launchpad/Lynch digest analytics and email builders."""

from __future__ import annotations

from datetime import date

from quant_hub.digest import policy as P
from quant_hub.digest.analytics import build_daily_payload, launchpad_actionable_tickers
from quant_hub.digest.humanize import daily_executive_summary, launchpad_why, weekly_executive_summary
from quant_hub.notify.digest_email import build_daily_digest_email, build_weekly_digest_email


def _launchpad_ticker(ticker: str, tier: str, score: float) -> dict:
    return {
        "ticker": ticker,
        "tier": tier,
        "sector_etf": "XLK",
        "tier_reason": "Tight base with MACD zero-line ignition.",
        "summary": {"final_adjusted_score": score, "normalized_score": score},
    }


class _FakeRepo:
    def __init__(self, report: dict, *, scan_date: date) -> None:
        self.report = report
        self.scan_date = scan_date
        self.run = {"id": 1, "scan_date": scan_date, "universe_id": P.DAILY_LAUNCHPAD_UNIVERSE}

    def get_latest_run(self, **kwargs):
        return self.run if kwargs.get("scan_date") == self.scan_date else None

    def load_report(self, **kwargs):
        return self.report if kwargs.get("scan_date") == self.scan_date else None

    def list_ticker_details_for_run(self, run_id: int):
        return self.report["tickers"]

    def list_runs_filtered(self, **kwargs):
        return [self.run]

    def list_runs(self, **kwargs):
        return [self.run]


def test_launchpad_actionable_tickers_sorts_by_score():
    rows = launchpad_actionable_tickers(
        [
            _launchpad_ticker("BBB", "Tier 2", 70.0),
            _launchpad_ticker("AAA", "Tier 1", 90.0),
            _launchpad_ticker("CCC", "Tier 3", 50.0),
        ]
    )
    assert [row["ticker"] for row in rows] == ["AAA", "BBB"]
    assert rows[0]["why"]
    assert "Launchpad" in rows[0]["tier_label"]


def test_build_daily_payload_omits_tier2_in_weak_regime():
    report = {
        "market_regime": {"label": "weak", "multiplier": 0.6, "spy_price": 500},
        "scan_summary": {"universe_size": 3, "eligible_count": 2},
        "tickers": [
            _launchpad_ticker("AAA", "Tier 1", 85.0),
            _launchpad_ticker("BBB", "Tier 2", 70.0),
        ],
    }
    payload = build_daily_payload(
        _FakeRepo(report, scan_date=date(2026, 6, 27)),
        scan_date=date(2026, 6, 27),
    )
    assert [row["ticker"] for row in payload["tier1"]] == ["AAA"]
    assert payload["tier2"] == []


def test_launchpad_why_uses_tier_reason():
    assert "MACD" in launchpad_why(_launchpad_ticker("AAA", "Tier 1", 90.0))


def test_daily_executive_summary_empty():
    lines = daily_executive_summary({"tier1": [], "tier2": [], "regime": {"label": "strong"}})
    assert "no actionable" in lines[0].lower()


def test_build_daily_digest_email_subject():
    payload = {
        "scan_date": "2026-06-27",
        "regime": {"label": "strong"},
        "tier1": [_launchpad_ticker("AAA", "Tier 1", 88)],
        "tier2": [],
        "new_entrants": ["AAA"],
        "dropped": [],
        "persistent": [],
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }
    subject, html = build_daily_digest_email(payload)
    assert "launchpad" in subject.lower()
    assert "AAA" in html
    assert "Daily Launchpad Brief" in html


def test_build_weekly_digest_email_overlap():
    payload = {
        "lynch_date": "2026-06-28",
        "launchpad_scan_date": "2026-06-27",
        "launchpad_overlap": [
            {
                "ticker": "NVDA",
                "launchpad": _launchpad_ticker("NVDA", "Tier 1", 90),
                "lynch": {
                    "lynch_score": 80,
                    "category_label": "Fast grower",
                    "why": "Fast grower with solid PEG.",
                },
            }
        ],
        "lynch_top": [],
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }
    subject, html = build_weekly_digest_email(payload)
    assert "launchpad overlap" in subject.lower()
    assert "NVDA" in html
    assert "Launchpad ∩ Lynch" in html


def test_weekly_executive_summary():
    lines = weekly_executive_summary(
        {
            "launchpad_overlap": [{"ticker": "NVDA"}],
            "lynch_top": [],
        }
    )
    assert "overlap" in lines[0].lower()
    assert "NVDA" in lines[1]
