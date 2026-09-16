"""Unit tests for Launchpad/Lynch digest analytics and email builders."""

from __future__ import annotations

from datetime import date

from quant_hub.digest import policy as P
from quant_hub.digest.analytics import build_daily_payload, launchpad_actionable_tickers
from quant_hub.digest.humanize import (
    daily_executive_summary,
    launchpad_factor_highlights,
    launchpad_setup_text,
    launchpad_why,
    weekly_executive_summary,
)
from quant_hub.notify.digest_email import build_daily_digest_email, build_weekly_digest_email


def _launchpad_ticker(ticker: str, tier: str, score: float, *, scores: dict | None = None) -> dict:
    return {
        "ticker": ticker,
        "tier": tier,
        "sector_etf": "XLK",
        "tier_reason": "Tight base with MACD zero-line ignition.",
        "summary": {"final_adjusted_score": score, "normalized_score": score},
        "scores": scores or {},
    }


def _digest_row(ticker: str, tier: str, score: float) -> dict:
    """A pre-built digest row, as `_launchpad_row` would output it."""
    return {
        "ticker": ticker,
        "tier": tier,
        "tier_label": tier,
        "final_score": score,
        "normalized_score": score,
        "sector_etf": "XLK",
        "tier_reason": "Tight base with MACD zero-line ignition.",
        "price": 100.0,
        "why": "Tight base with MACD zero-line ignition.",
        "factor_highlights": ["Extreme squeeze compression (ratio 0.82 < 0.90)"],
        "setup": "Watch for a breakout above EMA50 ($100.00) on expanding volume.",
    }


def _universe_payload(
    *,
    universe_id: str = "most_actives",
    tier1: list[dict] | None = None,
    tier2: list[dict] | None = None,
    near_misses: list[dict] | None = None,
    new_entrants: list[str] | None = None,
) -> dict:
    return {
        "universe_id": universe_id,
        "universe_label": P.UNIVERSE_LABELS.get(universe_id, universe_id),
        "tier1": tier1 or [],
        "tier2": tier2 or [],
        "near_misses": near_misses or [],
        "new_entrants": new_entrants or [],
        "dropped": [],
        "persistent": [],
    }


class _FakeRepo:
    """Fake ScanRepository keyed by universe_id so tests can cover multiple universes."""

    def __init__(self, universes: dict[str, dict], *, scan_date: date) -> None:
        self.universes = universes
        self.scan_date = scan_date
        self.runs = {
            universe_id: {"id": idx + 1, "scan_date": scan_date, "universe_id": universe_id}
            for idx, universe_id in enumerate(universes)
        }

    def get_latest_run(self, **kwargs):
        if kwargs.get("scan_date") != self.scan_date:
            return None
        return self.runs.get(kwargs.get("universe_id"))

    def load_report(self, **kwargs):
        if kwargs.get("scan_date") != self.scan_date:
            return None
        return self.universes.get(kwargs.get("universe_id"), {}).get("report")

    def list_ticker_details_for_run(self, run_id: int):
        for universe_id, run in self.runs.items():
            if run["id"] == run_id:
                return self.universes[universe_id]["tickers"]
        return []

    def list_runs_filtered(self, **kwargs):
        universe_id = kwargs.get("universe_id")
        return [self.runs[universe_id]] if universe_id in self.runs else []

    def list_runs(self, **kwargs):
        return list(self.runs.values())


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
    }
    tickers = [
        _launchpad_ticker("AAA", "Tier 1", 85.0),
        _launchpad_ticker("BBB", "Tier 2", 70.0),
    ]
    repo = _FakeRepo(
        {P.DAILY_LAUNCHPAD_UNIVERSE: {"report": report, "tickers": tickers}},
        scan_date=date(2026, 6, 27),
    )
    payload = build_daily_payload(repo, scan_date=date(2026, 6, 27))
    assert len(payload["universes"]) == 1
    universe = payload["universes"][0]
    assert [row["ticker"] for row in universe["tier1"]] == ["AAA"]
    assert universe["tier2"] == []
    assert payload["totals"] == {"tier1": 1, "tier2": 0, "near_misses": 0, "actionable": 1}


def test_build_daily_payload_skips_universe_missing_a_run():
    report = {
        "market_regime": {"label": "strong", "spy_price": 500},
        "scan_summary": {},
    }
    tickers = [_launchpad_ticker("AAA", "Tier 1", 85.0)]
    # Only most_actives has a run for this date; the other 3 configured universes don't.
    repo = _FakeRepo(
        {P.DAILY_LAUNCHPAD_UNIVERSE: {"report": report, "tickers": tickers}},
        scan_date=date(2026, 6, 27),
    )
    payload = build_daily_payload(repo, scan_date=date(2026, 6, 27))
    assert [u["universe_id"] for u in payload["universes"]] == [P.DAILY_LAUNCHPAD_UNIVERSE]


def test_build_daily_payload_surfaces_near_misses_when_no_actionable_hits():
    report = {
        "market_regime": {"label": "strong", "spy_price": 500},
        "scan_summary": {},
    }
    tickers = [
        _launchpad_ticker("AAA", "Tier 3", 60.0),
        _launchpad_ticker("BBB", "Tier 3", 55.0),
        _launchpad_ticker("CCC", "Tier 3", 50.0),
        _launchpad_ticker("DDD", "Tier 3", 45.0),
    ]
    repo = _FakeRepo(
        {P.DAILY_LAUNCHPAD_UNIVERSE: {"report": report, "tickers": tickers}},
        scan_date=date(2026, 6, 27),
    )
    payload = build_daily_payload(repo, scan_date=date(2026, 6, 27))
    universe = payload["universes"][0]
    assert universe["tier1"] == []
    assert universe["tier2"] == []
    assert [row["ticker"] for row in universe["near_misses"]] == ["AAA", "BBB", "CCC"]
    assert len(universe["near_misses"]) == P.DAILY_NEAR_MISS_MAX


def test_launchpad_why_uses_tier_reason():
    assert "MACD" in launchpad_why(_launchpad_ticker("AAA", "Tier 1", 90.0))


def test_launchpad_factor_highlights_from_scores():
    ticker = _launchpad_ticker(
        "AAA",
        "Tier 1",
        90.0,
        scores={
            "squeeze_intensity": {"score": 40, "meaning": "Extreme squeeze compression (ratio 0.82 < 0.90)"},
            "macd_zero_line": {"score": 0, "meaning": "MACD not igniting (inactive)"},
        },
    )
    highlights = launchpad_factor_highlights(ticker)
    assert highlights == ["Extreme squeeze compression (ratio 0.82 < 0.90)"]


def test_launchpad_setup_text_uses_trend_and_volume_raw():
    ticker = _launchpad_ticker(
        "AAA",
        "Tier 1",
        90.0,
        scores={
            "trend_proximity_match": {
                "raw": {"price_ema50": 182.4, "atr_distance": 1.2, "near_support_grade": "tight"}
            },
            "squeeze_intensity": {"raw": {"squeeze_ratio": 0.82}},
            "volume_vacuum_depth": {"raw": {"rvol": 0.38}},
        },
    )
    setup = launchpad_setup_text(ticker)
    assert "182.40" in setup
    assert "0.38" in setup
    assert "tight" in setup


def test_launchpad_setup_text_degrades_gracefully_without_raw_data():
    ticker = _launchpad_ticker("AAA", "Tier 1", 90.0, scores={})
    setup = launchpad_setup_text(ticker)
    assert setup


def test_daily_executive_summary_empty():
    payload = {
        "universes": [_universe_payload()],
        "regime": {"label": "strong"},
    }
    lines = daily_executive_summary(payload)
    assert "no actionable" in lines[0].lower()


def test_daily_executive_summary_mentions_near_misses_when_empty():
    payload = {
        "universes": [_universe_payload(near_misses=[{"ticker": "AAA"}])],
        "regime": {"label": "weak"},
    }
    lines = daily_executive_summary(payload)
    assert any("came close" in line.lower() for line in lines)


def test_daily_executive_summary_multi_universe_breakdown():
    payload = {
        "universes": [
            _universe_payload(universe_id="most_actives", tier1=[_digest_row("AAA", "Tier 1", 88)]),
            _universe_payload(universe_id="large_cap_growth", tier2=[_digest_row("BBB", "Tier 2", 70)]),
        ],
        "regime": {"label": "strong"},
    }
    lines = daily_executive_summary(payload)
    assert "2 actionable Launchpad names across 2 universes" in lines[0]
    assert "AAA" in lines[1]


def test_build_daily_digest_email_subject():
    universe = _universe_payload(tier1=[_digest_row("AAA", "Tier 1", 88)], new_entrants=["AAA"])
    payload = {
        "scan_date": "2026-06-27",
        "regime": {"label": "strong"},
        "universes": [universe],
        "totals": {"tier1": 1, "tier2": 0, "near_misses": 0, "actionable": 1},
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }
    subject, html = build_daily_digest_email(payload)
    assert "launchpad" in subject.lower()
    assert "AAA" in html
    assert "Daily Launchpad Brief" in html
    assert "Watch for a breakout" in html


def test_build_daily_digest_email_renders_near_misses_when_universe_empty():
    universe = _universe_payload(
        universe_id="small_cap_growth",
        near_misses=[_digest_row("ZZZ", "Tier 3", 62)],
    )
    payload = {
        "scan_date": "2026-06-27",
        "regime": {"label": "weak"},
        "universes": [universe],
        "totals": {"tier1": 0, "tier2": 0, "near_misses": 1, "actionable": 0},
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }
    subject, html = build_daily_digest_email(payload)
    assert "no qualified setups" in subject.lower()
    assert "ZZZ" in html
    assert "Closest to qualifying" in html


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
