"""Unit tests for digest analytics and email builders."""

from __future__ import annotations

from datetime import date

from quant_hub.digest.analytics import breakout_actionable_tickers, build_daily_payload
from quant_hub.digest import policy as P
from quant_hub.notify.digest_email import build_daily_digest_email, build_weekly_digest_email


def _breakout_ticker(ticker: str, tier: str, score: float) -> dict:
    return {
        "ticker": ticker,
        "tier": tier,
        "sector_etf": "XLK",
        "tier_reason": "test",
        "summary": {"final_adjusted_score": score, "normalized_score": score},
    }


def test_breakout_actionable_tickers_sorts_by_score():
    report = {
        "tickers": [
            _breakout_ticker("BBB", "Tier 2", 70.0),
            _breakout_ticker("AAA", "Tier 1", 90.0),
            _breakout_ticker("CCC", "Tier 3", 50.0),
        ]
    }
    rows = breakout_actionable_tickers(report)
    assert [r["ticker"] for r in rows] == ["AAA", "BBB"]


class _FakeRepo:
    def __init__(self, report: dict, *, scan_date: date) -> None:
        self._report = report
        self._scan_date = scan_date
        self._runs = [{"scan_date": scan_date, "universe_id": P.DAILY_BREAKOUT_UNIVERSE}]

    def load_report(self, **kwargs):
        if kwargs.get("scan_date") == self._scan_date:
            return self._report
        return None

    def list_runs(self, **kwargs):
        return self._runs


def test_build_daily_payload_tier1_only_in_weak_regime():
    report = {
        "market_regime": {"label": "weak", "multiplier": 0.6, "spy_price": 500},
        "scan_summary": {"universe_size": 3, "eligible_count": 2},
        "tickers": [
            _breakout_ticker("AAA", "Tier 1", 85.0),
            _breakout_ticker("BBB", "Tier 2", 70.0),
        ],
    }
    payload = build_daily_payload(_FakeRepo(report, scan_date=date(2026, 6, 27)), scan_date=date(2026, 6, 27))
    assert len(payload["tier1"]) == 1
    assert payload["tier1"][0]["ticker"] == "AAA"
    assert payload["tier2"] == []


def test_build_daily_digest_email_subject():
    payload = {
        "scan_date": "2026-06-27",
        "regime": {"label": "strong", "multiplier": 1.0, "spy_price": 550, "return_63d_pct": 5.2},
        "tier1": [{"ticker": "AAA", "tier": "Tier 1", "final_score": 88, "sector_etf": "XLK"}],
        "tier2": [],
        "new_entrants": ["AAA"],
        "dropped": [],
        "persistent": [],
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }
    subject, html = build_daily_digest_email(payload)
    assert "2026-06-27" in subject
    assert "1 conviction" in subject
    assert "AAA" in html


def test_build_weekly_digest_email_triple_count():
    payload = {
        "lynch_date": "2026-06-28",
        "swing_scan_date": "2026-06-27",
        "breakout_scan_date": "2026-06-27",
        "triple_alignment": [
            {
                "ticker": "NVDA",
                "breakout": {"tier": "Tier 1", "final_score": 90},
                "swing": {"tier": "SETUP_LONG", "swing_score": 85},
                "lynch": {"lynch_score": 80, "categories": ["fast_grower"]},
            }
        ],
        "swing_highlights": [],
        "lynch_top": [],
        "regime_week": [],
        "etf_highlights": [],
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }
    subject, html = build_weekly_digest_email(payload)
    assert "1 triple-alignment" in subject
    assert "NVDA" in html
