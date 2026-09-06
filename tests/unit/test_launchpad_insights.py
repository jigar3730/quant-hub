"""Launchpad Overview view-model tests."""

from __future__ import annotations

from datetime import date

from quant_hub.dashboard.viz.launchpad_insights import (
    build_launchpad_overview_vm,
    load_prior_report,
)


def _factor(
    score: float,
    *,
    max_pts: float,
    raw: dict | None = None,
) -> dict:
    return {"score": score, "max": max_pts, "raw": raw or {}}


def _ticker(
    symbol: str,
    *,
    eligible: bool,
    tier: str,
    final: float,
    sector: str = "XLK",
    fail_reason: str | None = None,
    squeeze: float = 0.0,
    tightness: float = 0.0,
    volume: float = 0.0,
    trend: float = 0.0,
    macd: float = 0.0,
    squeeze_ratio: float | None = None,
    tightness_rank: float | None = None,
    rvol: float | None = None,
    ema50_distance: float | None = None,
    macd_phase: str | None = None,
    tier_reason: str = "",
) -> dict:
    eligibility = {
        "passed": eligible,
        "fail_reason": None if eligible else fail_reason,
    }
    return {
        "ticker": symbol,
        "eligible": eligible,
        "tier": tier,
        "sector_etf": sector,
        "tier_reason": tier_reason
        or (
            "High conviction"
            if tier == "Tier 1"
            else "Watchlist"
            if tier == "Tier 2"
            else "Below watchlist threshold"
            if eligible
            else fail_reason or ""
        ),
        "eligibility": eligibility,
        "filter_reason": None if eligible else fail_reason,
        "summary": {
            "final_adjusted_score": final,
            "normalized_score": final,
            "raw_score": final,
        },
        "scores": {
            "squeeze_intensity": _factor(
                squeeze, max_pts=40, raw={"squeeze_ratio": squeeze_ratio}
            ),
            "tightness_percentile": _factor(
                tightness, max_pts=15, raw={"tightness_rank_pct": tightness_rank}
            ),
            "volume_vacuum_depth": _factor(volume, max_pts=30, raw={"rvol": rvol}),
            "trend_proximity_match": _factor(
                trend, max_pts=15, raw={"pct_distance": ema50_distance}
            ),
            "macd_zero_line": _factor(macd, max_pts=25, raw={"phase": macd_phase}),
        },
    }


def _report(tickers: list[dict], *, scan_date: str = "2026-09-06", universe_id: str = "most_active") -> dict:
    eligible = sum(1 for t in tickers if t["eligible"])
    t1 = sum(1 for t in tickers if t["tier"] == "Tier 1")
    t2 = sum(1 for t in tickers if t["tier"] == "Tier 2")
    return {
        "strategy_id": "launchpad",
        "universe_id": universe_id,
        "scan_date": scan_date,
        "scan_summary": {
            "universe_size": len(tickers),
            "eligible_count": eligible,
            "excluded_count": len(tickers) - eligible,
            "tier_counts": {
                "Tier 1": t1,
                "Tier 2": t2,
                "Tier 3": sum(1 for t in tickers if t["tier"] == "Tier 3"),
                "filtered": sum(1 for t in tickers if t["tier"] == "filtered"),
            },
            "actionable_count": t1 + t2,
        },
        "market_regime": {"label": "uptrend", "multiplier": 1.0},
        "tickers": tickers,
    }


def _sofi_scan() -> list[dict]:
    return [
        _ticker(
            "NVDA",
            eligible=True,
            tier="Tier 1",
            final=88.0,
            squeeze=40,
            tightness=15,
            volume=18,
            trend=15,
            macd=25,
            squeeze_ratio=0.84,
            tightness_rank=0.06,
            rvol=0.40,
            ema50_distance=0.012,
            macd_phase="zero_line_ignition",
        ),
        _ticker(
            "AAPL",
            eligible=True,
            tier="Tier 2",
            final=72.0,
            squeeze=25,
            tightness=0,
            volume=30,
            trend=8,
            macd=0,
            squeeze_ratio=0.96,
            tightness_rank=0.22,
            rvol=0.44,
            ema50_distance=0.03,
            macd_phase="inactive",
            sector="XLK",
        ),
        _ticker(
            "SOFI",
            eligible=False,
            tier="filtered",
            final=85.0,
            fail_reason="macro_trend_not_aligned",
            squeeze=40,
            tightness=15,
            volume=30,
            trend=0,
            macd=25,
            squeeze_ratio=0.81,
            tightness_rank=0.05,
            rvol=0.38,
            ema50_distance=0.04,
            macd_phase="zero_line_ignition",
            sector="XLF",
            tier_reason="Price not above the 200-day EMA",
        ),
        _ticker(
            "NEAR",
            eligible=True,
            tier="Tier 3",
            final=62.0,
            squeeze=25,
            tightness=0,
            volume=15,
            trend=8,
            macd=0,
            squeeze_ratio=0.99,
            tightness_rank=0.30,
            rvol=0.70,
            ema50_distance=0.02,
        ),
        _ticker(
            "CHEAP",
            eligible=False,
            tier="filtered",
            final=20.0,
            fail_reason="price_below_10",
            squeeze=0,
            sector="XLF",
        ),
        _ticker(
            "FAR",
            eligible=False,
            tier="filtered",
            final=40.0,
            fail_reason="structural_proximity",
            squeeze=25,
            sector="XLE",
        ),
    ]


def test_blocked_sofi_is_not_in_factor_mix_or_actionable_grid():
    vm = build_launchpad_overview_vm(_report(_sofi_scan()))
    mix = {row["label"]: row for row in vm["drivers"]["factor_mix"]}
    assert vm["drivers"]["cohort_size"] == 2
    assert "SOFI" not in {row["ticker"] for row in vm["drivers"]["top_contributions"]}
    assert "SOFI" not in {row["ticker"] for row in vm["grid"]["actionable"]}
    # Mix is NVDA+AAPL only: squeeze mean (40+25)/2 = 32.5
    assert mix["Squeeze Intensity"]["mean_points"] == 32.5


def test_blocked_sofi_appears_on_blocked_and_coil_tabs():
    vm = build_launchpad_overview_vm(_report(_sofi_scan()))
    blocked = {row["ticker"]: row for row in vm["grid"]["blocked"]}
    assert "SOFI" in blocked
    assert blocked["SOFI"]["status"] == "Blocked ≥80"
    assert blocked["SOFI"]["final_score"] == 85.0
    assert blocked["SOFI"]["filter_reason"] == "macro_trend_not_aligned"
    assert "200-day" in blocked["SOFI"]["reason"]
    coils = [row["ticker"] for row in vm["grid"]["coils"]]
    assert coils[0] == "SOFI"
    assert "CHEAP" not in coils


def test_near_miss_and_actionable_tabs():
    vm = build_launchpad_overview_vm(_report(_sofi_scan()))
    assert {row["ticker"] for row in vm["grid"]["actionable"]} == {"NVDA", "AAPL"}
    assert {row["ticker"] for row in vm["grid"]["near_miss"]} == {"NEAR"}


def test_funnel_counts_include_blocked_high_score():
    vm = build_launchpad_overview_vm(_report(_sofi_scan()))
    by_id = {stage["id"]: stage for stage in vm["funnel"]["stages"]}
    assert by_id["universe"]["remaining"] == 6
    assert by_id["tradable"]["dropped"] == 1  # CHEAP
    assert by_id["macro"]["dropped"] == 1  # SOFI
    assert by_id["eligible"]["dropped"] == 1  # FAR
    assert by_id["eligible"]["remaining"] == 3
    assert by_id["watchlist"]["remaining"] == 2
    assert by_id["tier1"]["remaining"] == 1


def test_headline_calls_out_blocked_sofi():
    vm = build_launchpad_overview_vm(_report(_sofi_scan()))
    headline = vm["takeaway"]["headline"]
    assert "SOFI" in headline
    assert "blocked setup" in headline
    assert vm["takeaway"]["blocked_count"] == 1
    assert vm["takeaway"]["blocked_high_count"] == 1


def test_scan_delta_new_dropped_and_upgrade():
    current = _sofi_scan()
    prior = [
        _ticker("NVDA", eligible=True, tier="Tier 2", final=70.0),
        _ticker("OLD", eligible=True, tier="Tier 2", final=71.0),
        _ticker("SOFI", eligible=False, tier="filtered", final=80.0, fail_reason="macro_trend_not_aligned"),
    ]
    vm = build_launchpad_overview_vm(
        _report(current, scan_date="2026-09-06"),
        _report(prior, scan_date="2026-09-04"),
    )
    new_names = {row["ticker"] for row in vm["delta"]["new_actionable"]}
    dropped = {row["ticker"] for row in vm["delta"]["dropped_actionable"]}
    upgraded = {row["ticker"] for row in vm["delta"]["upgraded"]}
    assert "AAPL" in new_names
    assert "OLD" in dropped
    assert "NVDA" in upgraded
    nvda = next(row for row in vm["grid"]["actionable"] if row["ticker"] == "NVDA")
    assert nvda["score_delta"] == 18.0
    assert "2026-09-04" in vm["takeaway"]["headline"]


def test_factor_mix_empty_when_only_blocked_names():
    tickers = [
        _ticker(
            "SOFI",
            eligible=False,
            tier="filtered",
            final=85.0,
            fail_reason="macro_trend_not_aligned",
            squeeze=40,
        )
    ]
    vm = build_launchpad_overview_vm(_report(tickers))
    assert vm["drivers"]["cohort_size"] == 0
    assert vm["grid"]["actionable"] == []
    assert vm["grid"]["blocked"][0]["ticker"] == "SOFI"


def test_load_prior_report_skips_current_date():
    class _Repo:
        def list_runs_filtered(self, **kwargs):
            return [
                {"scan_date": date(2026, 9, 6), "id": 2},
                {"scan_date": date(2026, 9, 4), "id": 1},
            ]

        def load_report(self, **kwargs):
            assert kwargs["scan_date"] == date(2026, 9, 4)
            return {"scan_date": "2026-09-04", "tickers": []}

    prior = load_prior_report(
        _Repo(),
        strategy_id="launchpad",
        universe_id="most_active",
        scan_date="2026-09-06",
    )
    assert prior["scan_date"] == "2026-09-04"


def test_sector_concentration_warns_when_book_is_one_etf():
    tickers = [
        _ticker("AAA", eligible=True, tier="Tier 1", final=90, macd=25, squeeze=40),
        _ticker("BBB", eligible=True, tier="Tier 2", final=70, squeeze=25),
        _ticker("CCC", eligible=True, tier="Tier 2", final=68, squeeze=25),
        _ticker("DDD", eligible=True, tier="Tier 1", final=82, macd=25, squeeze=40),
    ]
    vm = build_launchpad_overview_vm(_report(tickers))
    assert vm["sector"]["dominant_sector"] == "XLK"
    assert vm["sector"]["concentration_warning"] is True
