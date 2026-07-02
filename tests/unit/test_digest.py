"""Unit tests for digest analytics and email builders."""

from __future__ import annotations

from datetime import date

from quant_hub.digest import policy as P
from quant_hub.digest.analytics import breakout_actionable_tickers, build_daily_payload
from quant_hub.digest.humanize import (
    breakout_why,
    daily_executive_summary,
    friendly_swing_tier,
    lynch_why,
    swing_why,
    weekly_executive_summary,
)
from quant_hub.notify.digest_email import build_daily_digest_email, build_weekly_digest_email


def _breakout_ticker(ticker: str, tier: str, score: float) -> dict:
    return {
        "ticker": ticker,
        "tier": tier,
        "sector_etf": "XLK",
        "tier_reason": "Compression and volume confirm the setup.",
        "summary": {"final_adjusted_score": score, "normalized_score": score},
        "scores": {"compression": {"score": 9, "max": 10}},
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
    assert rows[0]["why"]
    assert rows[0]["tier_label"] == "High conviction breakout"


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
    assert payload["tier1"][0]["why"]
    assert payload["tier2"] == []


def test_breakout_why_uses_tier_reason():
    why = breakout_why(_breakout_ticker("AAA", "Tier 1", 90.0))
    assert "Compression" in why


def test_swing_why_from_rule_breakdown():
    ticker = {
        "tier_reason": "Pullback into rising EMA",
        "setup_detail": {
            "rule_breakdown": [
                {"label": "Trend intact", "passed": True, "score": 25, "max": 30},
                {"label": "RSI reset", "passed": True, "score": 20, "max": 25},
            ],
            "rsi": 42.5,
        },
    }
    why = swing_why(ticker)
    assert "Pullback" in why
    assert "Trend intact" in why


def test_lynch_why_prefers_investor_summary():
    why = lynch_why(
        {
            "investor_summary": "Fast grower with reasonable PEG and strong earnings trend.",
            "categories": ["fast_grower"],
            "peg_ratio": 0.8,
        }
    )
    assert "Fast grower" in why


def test_friendly_swing_tier():
    assert friendly_swing_tier("SETUP_LONG") == "Pullback long"


def test_daily_executive_summary_empty():
    lines = daily_executive_summary(
        {"tier1": [], "tier2": [], "regime": {"label": "strong", "spy_price": 550, "return_63d_pct": 5.2}}
    )
    assert "no S&P 500" in lines[0].lower() or "strict" in lines[0].lower()


def test_build_daily_digest_email_subject():
    payload = {
        "scan_date": "2026-06-27",
        "regime": {"label": "strong", "multiplier": 1.0, "spy_price": 550, "return_63d_pct": 5.2},
        "tier1": [
            {
                "ticker": "AAA",
                "tier": "Tier 1",
                "tier_label": "High conviction breakout",
                "final_score": 88,
                "sector_etf": "XLK",
                "why": "Strong compression with volume confirmation.",
            }
        ],
        "tier2": [],
        "new_entrants": ["AAA"],
        "dropped": [],
        "persistent": [],
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }
    subject, html = build_daily_digest_email(payload)
    assert "high-conviction" in subject.lower() or "high conviction" in subject.lower()
    assert "AAA" in html
    assert "Why" not in html  # prose is inline, not a column header
    assert "Strong compression" in html
    assert "Daily Breakout Brief" in html


def test_build_daily_digest_email_empty_state():
    payload = {
        "scan_date": "2026-06-27",
        "regime": {"label": "strong", "multiplier": 1.0, "spy_price": 550, "return_63d_pct": 5.2},
        "tier1": [],
        "tier2": [],
        "new_entrants": [],
        "dropped": [],
        "persistent": [],
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }
    subject, html = build_daily_digest_email(payload)
    assert "quiet" in subject.lower()
    assert "weekly digest" in html.lower()


def test_build_weekly_digest_email_triple_count():
    payload = {
        "lynch_date": "2026-06-28",
        "swing_scan_date": "2026-06-27",
        "breakout_scan_date": "2026-06-27",
        "triple_alignment": [
            {
                "ticker": "NVDA",
                "breakout": {
                    "tier": "Tier 1",
                    "final_score": 90,
                    "why": "Breakout with volume.",
                },
                "swing": {
                    "tier": "SETUP_LONG",
                    "tier_label": "Pullback long",
                    "swing_score": 85,
                    "why": "Pullback into EMA.",
                },
                "lynch": {
                    "lynch_score": 80,
                    "categories": ["fast_grower"],
                    "category_label": "Fast grower",
                    "why": "Fast grower with solid PEG.",
                },
            }
        ],
        "swing_highlights": [],
        "lynch_top": [],
        "regime_week": [],
        "etf_highlights": [],
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }
    subject, html = build_weekly_digest_email(payload)
    assert "triple hit" in subject.lower()
    assert "NVDA" in html
    assert "Triple alignment" in html


def test_weekly_executive_summary():
    lines = weekly_executive_summary(
        {
            "triple_alignment": [{"ticker": "NVDA"}],
            "swing_highlights": [],
            "lynch_top": [],
        }
    )
    assert "triple-alignment" in lines[0].lower()
    assert "NVDA" in lines[1]
