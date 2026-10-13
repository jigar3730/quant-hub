"""Scan pipeline: tiering, filter reasons, regime gate, portfolio gates, freshness, isolation."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest
from swing_fixtures import (
    END,
    TAIL_EXTENDED,
    TAIL_TRIGGER,
    TAIL_WATCH,
    TAIL_WIDE_STOP,
    FakeLoader,
    bear_spy_closes,
    etf,
    make_frame,
    market,
    path,
    scenario,
)

from quant_hub.sector_swing import config as C
from quant_hub.sector_swing import runner as runner_mod
from quant_hub.sector_swing.calendar import ET
from quant_hub.sector_swing.models import TickerOutcome
from quant_hub.sector_swing.runner import (
    MissingBenchmarkError,
    SectorSwingRunner,
    StaleDataError,
    scan_prices,
)
from quant_hub.serialization.json_util import json_dumps

WIDE = replace(C.DEFAULT_PARAMS, top_n_leaders=16)  # keep leadership out of the way
MONDAY_PREMARKET = datetime(2026, 9, 21, 5, 20, tzinfo=ET)  # expected session = Fri 2026-09-18


def scan(prices, universe, params=WIDE, **kw):
    kw.setdefault("equity", 50_000)
    kw.setdefault("risk_pct", 0.01)
    return scan_prices(prices, universe, params=params, **kw)


def by_ticker(result) -> dict[str, TickerOutcome]:
    return {o.ticker: o for o in result.outcomes}


# ---------- tiering: one fixture per tier / reason ----------
def test_each_tier_and_reason():
    prices = pd.concat(
        [
            scenario(
                TRIG=TAIL_TRIGGER,
                WIDE=TAIL_WIDE_STOP,
                WATCH=TAIL_WATCH,
                EXT=TAIL_EXTENDED,
                CRASH=(-0.02,) * 8,  # strong 126d RS, but closes below SMA50
            ),
            etf("FLAT", daily=0.0001),  # lags SPY: RS < 0
            etf("THIN", TAIL_TRIGGER, volume=1_000),  # dollar volume far below the floor
            etf("SHORT", TAIL_TRIGGER, n=150),  # < 210 bars
            make_frame("SPIKE", path(50, 0.004, tail=(3.0,))),  # last close 4x prior median
        ],
        ignore_index=True,
    )
    out = by_ticker(scan(prices, ["TRIG", "WIDE", "WATCH", "EXT", "CRASH", "FLAT", "THIN",
                                  "SHORT", "SPIKE", "GONE"]))

    assert out["TRIG"].tier == C.TIER_TRIGGER
    assert out["TRIG"].plan and out["TRIG"].plan.shares > 0 and not out["TRIG"].plan.regime_blocked
    assert out["WATCH"].tier == C.TIER_WATCH and not out["WATCH"].regime_blocked
    assert out["EXT"].tier == C.TIER_EXTENDED
    expected = {
        "WIDE": C.REASON_STOP_TOO_WIDE,
        "CRASH": C.REASON_TREND_FAIL,
        "FLAT": C.REASON_NOT_LEADER,
        "THIN": C.REASON_ILLIQUID,
        "SHORT": C.REASON_INSUFFICIENT_HISTORY,
        "SPIKE": C.REASON_DATA_QUALITY,
        "GONE": C.REASON_NO_PRICE_DATA,
    }
    for ticker, reason in expected.items():
        assert out[ticker].tier == C.TIER_FILTERED, ticker
        assert out[ticker].reason == reason, ticker
        assert out[ticker].plan is None


def test_trigger_plan_geometry():
    out = by_ticker(scan(scenario(TRIG=TAIL_TRIGGER), ["TRIG"]))["TRIG"]
    plan, ind = out.plan, out.indicators
    assert plan.entry_ref == ind.close
    assert plan.stop == pytest.approx(ind.pullback_low - 0.25 * ind.atr14)
    assert plan.target_2r == pytest.approx(plan.entry_ref + 2 * plan.risk_per_share)
    assert plan.chase_limit == pytest.approx(ind.close + 0.5 * ind.atr14)
    assert plan.stop_atr_multiple <= 2.5
    # 30% position cap binds here: floor(0.30 * 50k / entry)
    assert plan.shares == int(0.30 * 50_000 // plan.entry_ref)


def test_top_n_leaders_cutoff_with_default_params():
    # Five positive-RS ETFs; only the top 4 are leaders, the 5th is not_leader despite RS > 0.
    drifts = {"E1": 0.0060, "E2": 0.0055, "E3": 0.0050, "E4": 0.0045, "E5": 0.0030}
    prices = market(*[etf(t, TAIL_EXTENDED, daily=d) for t, d in drifts.items()])
    out = by_ticker(scan(prices, list(drifts), params=C.DEFAULT_PARAMS))
    assert [out[t].rs_rank for t in drifts] == [1, 2, 3, 4, 5]
    assert out["E5"].rs_score_pct > 0
    assert out["E5"].tier == C.TIER_FILTERED and out["E5"].reason == C.REASON_NOT_LEADER
    assert all(out[t].tier != C.TIER_FILTERED for t in ("E1", "E2", "E3", "E4"))


# ---------- regime gate ----------
def test_regime_off_yields_no_tier1_and_marks_blocked_setups():
    prices = scenario(spy=bear_spy_closes(), TRIG=TAIL_TRIGGER, WATCH=TAIL_WATCH)
    result = scan(prices, ["TRIG", "WATCH"])
    out = by_ticker(result)

    assert not result.regime_gate_passed
    assert all(o.tier != C.TIER_TRIGGER for o in result.outcomes)
    trig = out["TRIG"]
    assert trig.tier == C.TIER_WATCH and trig.regime_blocked
    assert trig.plan is not None and trig.plan.regime_blocked  # informational levels only
    assert out["WATCH"].tier == C.TIER_WATCH and not out["WATCH"].regime_blocked


def test_regime_gate_uses_unrounded_smas():
    # SPY flat at 100 then a last close of 100.004: unrounded it is above both SMAs, but the
    # repo's regime_detail() rounds to 2dp, where price == SMA50 == 100.0 (a rounded compare fails).
    spy = [100.0] * 259 + [100.004]
    result = scan(market(spy=spy), [])
    assert result.regime["spy_price"] == result.regime["sma50"] == 100.0
    assert result.regime_gate_passed


# ---------- portfolio gates ----------
def _outcome(ticker, rank):
    from quant_hub.sector_swing.models import TradePlan

    plan = TradePlan(100, 95, 5, 2, 110, 101, 95, 50, 250, 5000)
    return TickerOutcome(ticker, C.TIER_FILTERED, rs_rank=rank, plan=plan)


def _walk(ticker, seed):
    return make_frame(ticker, path(50, 0.0, seed=seed, sigma=0.01))


def test_signal_cap_and_independent_candidates():
    frames = {t: _walk(t, s) for t, s in zip("ABCD", (1, 2, 3, 4), strict=True)}
    cands = [_outcome(t, i + 1) for i, t in enumerate("ABCD")]
    runner_mod._apply_portfolio_gates(cands, frames, C.DEFAULT_PARAMS)

    assert [c.tier for c in cands] == [C.TIER_TRIGGER] * 3 + [C.TIER_FILTERED]
    assert cands[3].reason == C.REASON_SIGNAL_CAP and cands[3].plan is None


def test_correlation_gate_skips_near_duplicate():
    a = path(50, 0.0, seed=11, sigma=0.01)
    twin = list(np.asarray(a) * (1 + np.random.default_rng(5).normal(0, 0.0004, len(a))))
    frames = {"A": make_frame("A", a), "TWIN": make_frame("TWIN", twin), "C": _walk("C", 99)}
    cands = [_outcome("A", 1), _outcome("TWIN", 2), _outcome("C", 3)]
    runner_mod._apply_portfolio_gates(cands, frames, C.DEFAULT_PARAMS)

    assert cands[0].tier == C.TIER_TRIGGER
    assert cands[1].tier == C.TIER_FILTERED and cands[1].reason == C.REASON_CORRELATED
    assert cands[1].plan is None
    assert cands[2].tier == C.TIER_TRIGGER  # unrelated series still passes
    corr_checks = [c for c in cands[1].checks if c.rule == "P_correlation"]
    assert corr_checks and corr_checks[0].value > 0.85 and not corr_checks[0].passed


def test_correlation_gate_end_to_end_with_identical_series():
    prices = pd.concat(
        [scenario(TRIG=TAIL_TRIGGER), etf("TRIGB", TAIL_TRIGGER)], ignore_index=True
    )
    out = by_ticker(scan(prices, ["TRIG", "TRIGB"]))
    assert out["TRIG"].tier == C.TIER_TRIGGER  # tie on RS -> ticker order decides
    assert out["TRIGB"].tier == C.TIER_FILTERED and out["TRIGB"].reason == C.REASON_CORRELATED


def test_correlation_gate_ignores_undefined_correlation():
    flat = make_frame("F", [50.0] * 260)  # zero-variance returns -> NaN correlation
    frames = {"A": _walk("A", 1), "F": flat}
    cands = [_outcome("A", 1), _outcome("F", 2)]
    runner_mod._apply_portfolio_gates(cands, frames, C.DEFAULT_PARAMS)
    assert cands[1].tier == C.TIER_TRIGGER  # gate skipped (logged), not crashed


# ---------- failure isolation ----------
def test_one_ticker_raising_does_not_abort_the_run(monkeypatch):
    real = runner_mod.compute_indicators

    def flaky(df, params):
        if df["ticker"].iloc[0] == "BAD":
            raise ZeroDivisionError("boom")
        return real(df, params)

    monkeypatch.setattr(runner_mod, "compute_indicators", flaky)
    out = by_ticker(scan(scenario(TRIG=TAIL_TRIGGER, BAD=TAIL_TRIGGER), ["TRIG", "BAD"]))

    assert out["BAD"].tier == C.TIER_FILTERED and out["BAD"].reason == C.REASON_COMPUTE_ERROR
    assert "ZeroDivisionError" in out["BAD"].error
    assert out["TRIG"].tier == C.TIER_TRIGGER


def test_rule_evaluation_error_is_isolated(monkeypatch):
    def boom(ind, params):
        raise RuntimeError("rule blew up")

    monkeypatch.setattr(runner_mod.rules, "check_trend", boom)
    out = by_ticker(scan(scenario(TRIG=TAIL_TRIGGER), ["TRIG"]))
    assert out["TRIG"].reason == C.REASON_COMPUTE_ERROR and out["TRIG"].plan is None


def test_missing_spy_aborts():
    with pytest.raises(MissingBenchmarkError):
        scan(etf("TRIG", TAIL_TRIGGER), ["TRIG"])


def test_short_spy_history_aborts_instead_of_crashing():
    prices = scenario(spy=path(100, 0.0005, 150), TRIG=TAIL_TRIGGER)
    with pytest.raises(MissingBenchmarkError, match="Insufficient SPY history"):
        scan(prices, ["TRIG"])


# ---------- no look-ahead ----------
def test_scan_at_t_ignores_everything_after_t():
    n_total, t_idx = 275, 259
    trig = path(50, 0.004, t_idx + 1, TAIL_TRIGGER)  # trigger setup on bar t
    spy = path(100, 0.0005, t_idx + 1)
    crash = [-0.15] * (n_total - t_idx - 1)  # garbage future

    def build(future):
        def ext(closes, steps):
            out = list(closes)
            for s in steps:
                out.append(out[-1] * (1 + s))
            return out

        return pd.concat(
            [make_frame("SPY", ext(spy, future)), make_frame("TRIG", ext(trig, future))],
            ignore_index=True,
        )

    calm, wild = build([0.0005] * len(crash)), build(crash)
    t = pd.bdate_range(end=END, periods=n_total)[t_idx].date()
    truncated_only = pd.concat(
        [make_frame("SPY", spy, end=t), make_frame("TRIG", trig, end=t)], ignore_index=True
    )

    def view(res):
        o = res.outcomes[0]
        return (o.tier, o.reason, o.rs_score_pct, o.plan, [c.to_dict() for c in o.checks],
                res.regime, res.spy_as_of)

    at_t_calm = view(scan(calm, ["TRIG"], as_of=t))
    at_t_wild = view(scan(wild, ["TRIG"], as_of=t))
    on_truncated = view(scan(truncated_only, ["TRIG"]))

    assert at_t_calm == at_t_wild == on_truncated
    assert at_t_calm[0] == C.TIER_TRIGGER
    assert view(scan(wild, ["TRIG"]))[0] != C.TIER_TRIGGER  # without as_of the crash is visible


# ---------- data freshness ----------
def run_runner(loader, **kw):
    kw.setdefault("now", MONDAY_PREMARKET)
    kw.setdefault("equity", 50_000)
    return SectorSwingRunner(
        universe=["TRIG", "WATCH"], price_loader=loader, params=WIDE, **kw
    ).run()


FRESH = scenario(TRIG=TAIL_TRIGGER, WATCH=TAIL_WATCH)  # last bar Fri 2026-09-18
STALE = scenario(end=pd.Timestamp("2026-09-16"), TRIG=TAIL_TRIGGER, WATCH=TAIL_WATCH)


def test_fresh_data_single_fetch():
    loader = FakeLoader(FRESH)
    _, report = run_runner(loader)
    assert loader.calls == [True]
    assert report["market_regime"]["data_freshness"] == C.FRESHNESS_FRESH
    assert report["market_regime"]["as_of_price"] == "2026-09-18"
    assert report["data_provenance"]["expected_session"] == "2026-09-18"


def test_stale_cache_triggers_one_cache_bypass_refetch():
    loader = FakeLoader(STALE, FRESH)
    _, report = run_runner(loader)
    assert loader.calls == [True, False]  # cached first, then bypassing the cache
    assert report["market_regime"]["data_freshness"] == C.FRESHNESS_REFRESHED
    assert report["market_regime"]["as_of_price"] == "2026-09-18"


def test_still_stale_after_refetch_is_a_hard_failure():
    loader = FakeLoader(STALE, STALE)
    with pytest.raises(StaleDataError, match="Stale price data"):
        run_runner(loader)
    assert loader.calls == [True, False]


def test_force_refresh_does_not_refetch_twice():
    loader = FakeLoader(STALE)
    with pytest.raises(StaleDataError):
        run_runner(loader, use_cache=False)
    assert loader.calls == [False]


def test_allow_stale_is_recorded():
    loader = FakeLoader(STALE, STALE)
    _, report = run_runner(loader, allow_stale=True)
    assert report["market_regime"]["data_freshness"] == C.FRESHNESS_STALE_ALLOWED
    assert report["data_provenance"]["data_freshness"] == C.FRESHNESS_STALE_ALLOWED
    assert report["market_regime"]["as_of_price"] == "2026-09-16"


def test_partial_bar_for_today_is_dropped():
    # Monday's bar (dated 2026-09-21) exists before that session closed.
    with_partial = scenario(end=pd.Timestamp("2026-09-21"), TRIG=TAIL_TRIGGER, WATCH=TAIL_WATCH)
    loader = FakeLoader(with_partial)
    _, report = run_runner(loader)
    assert report["market_regime"]["as_of_price"] == "2026-09-18"
    assert report["market_regime"]["data_freshness"] == C.FRESHNESS_FRESH
    assert all(t["indicators"]["bar_date"] == "2026-09-18"
               for t in report["tickers"] if "indicators" in t)


def test_missing_benchmark_after_refetch_is_fatal():
    loader = FakeLoader(etf("TRIG", TAIL_TRIGGER))
    with pytest.raises(MissingBenchmarkError):
        run_runner(loader)
    assert loader.calls == [True, False]


def test_dry_run_skips_freshness_gate():
    loader = FakeLoader()  # must never be called
    df, report = SectorSwingRunner(
        universe=["XLK", "XLE"], dry_run=True, price_loader=loader, equity=50_000
    ).run()
    assert loader.calls == []
    assert report["market_regime"]["data_freshness"] == C.FRESHNESS_SYNTHETIC
    assert report["data_provenance"]["dry_run"] is True
    assert len(df) == 2


# ---------- report payload ----------
def test_report_shape_and_json_safety():
    _, report = run_runner(FakeLoader(FRESH))

    # Everything must survive the repo's Postgres JSON encoder (no numpy scalars / dates).
    roundtrip = json.loads(json_dumps(report))
    assert roundtrip["strategy_id"] == "sector_etf_swing"

    summary = report["scan_summary"]
    assert set(summary["tier_counts"]) == {"Tier 1", "Tier 2", "Tier 3", "filtered"}
    assert summary["actionable_count"] == summary["tier_counts"]["Tier 1"] == 1
    assert summary["eligible_count"] == 2 and summary["universe_size"] == 2

    prov = report["data_provenance"]
    assert prov["schema_version"] == C.SCHEMA_VERSION
    assert prov["equity_assumed"] == 50_000 and prov["risk_pct"] == 0.01
    assert len(prov["config_hash"]) == 12

    regime = report["market_regime"]
    assert regime["regime_gate_passed"] is True
    assert {"label", "multiplier", "sma50", "sma200", "spy_price"} <= set(regime)

    trig = next(t for t in report["tickers"] if t["ticker"] == "TRIG")
    assert trig["schema_version"] == 1 and trig["sector_etf"] == "SPY"
    assert trig["tier"] == "Tier 1" and trig["eligible"] is True
    assert trig["summary"]["final_adjusted_score"] == trig["summary"]["rs_score_pct"]
    assert trig["eligibility"]["passed"] is True and trig["eligibility"]["fail_reason"] is None
    check = trig["eligibility"]["checks"][0]
    assert set(check) == {"rule", "passed", "value", "threshold"}  # matches frontend EligibilityCheck
    assert {"entry_ref", "stop", "target_2r", "chase_limit", "shares", "invalidation"} <= set(
        trig["trade_plan"]
    )
    watch = next(t for t in report["tickers"] if t["ticker"] == "WATCH")
    assert watch["tier"] == "Tier 2" and "trade_plan" not in watch


def test_filtered_row_carries_reason_for_repository_columns():
    prices = scenario(TRIG=TAIL_TRIGGER)
    result = scan(prices, ["TRIG", "GONE"])
    from quant_hub.sector_swing.report import build_report

    report = build_report(
        result, universe=["TRIG", "GONE"], universe_id="sector_etfs", params=WIDE,
        equity=50_000, risk_pct=0.01, data_freshness="fresh", expected_session=date(2026, 9, 18),
        scan_date=date(2026, 9, 21), price_cache="live", dry_run=False,
    )
    gone = next(t for t in report["tickers"] if t["ticker"] == "GONE")
    assert gone["eligibility"]["fail_reason"] == "no_price_data" and gone["eligible"] is False
    assert gone["summary"]["final_adjusted_score"] is None
    assert report["scan_summary"]["filter_breakdown"] == {"no_price_data": 1}
    assert report["scan_summary"]["tickers_failed"] == 1


def test_markdown_summary_mentions_plans_and_disclaimer():
    from quant_hub.sector_swing.report import render_markdown

    _, report = run_runner(FakeLoader(FRESH))
    md = render_markdown(report)
    assert "| TRIG |" in md and "Chase limit" in md
    assert "not investment advice" in md and "PASS" in md
