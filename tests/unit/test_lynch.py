import pandas as pd
from pathlib import Path

from quant_hub.lynch.categories import (
    assign_categories,
    classify_asset_play,
    classify_fast_grower,
    classify_stalwart,
)
from quant_hub.lynch.filters import apply_anti_filters, apply_base_screen, lynch_score
from quant_hub.lynch.metrics import compute_peg, normalize_debt_to_equity
from quant_hub.lynch.runner import LynchScannerRunner
from quant_hub.notify.email import build_lynch_email


def _ideal_metrics(**overrides) -> dict:
    base = {
        "ticker": "TEST",
        "trailing_eps": 2.5,
        "pe_ratio": 15.0,
        "peg_ratio": 0.8,
        "eps_growth_5y": 0.20,
        "eps_growth_for_peg": 0.20,
        "eps_growth_source": "TTM EPS vs prior 4 quarters",
        "debt_to_equity": 0.20,
        "net_cash": 500_000_000,
        "institutional_ownership": 0.30,
        "analyst_count": 3,
        "insider_purchases_6m": 10000.0,
        "shares_outstanding_change_yoy": -0.02,
        "market_cap": 2_000_000_000,
        "dividend_yield": 0.02,
        "price_to_book": 0.8,
        "net_cash_price_ratio": 0.35,
        "return_on_equity": 0.18,
        "revenue_cv": 0.15,
    }
    base.update(overrides)
    return base


def test_normalize_debt_to_equity_percent():
    assert normalize_debt_to_equity(35.0) == 0.35
    assert normalize_debt_to_equity(0.25) == 0.25
    assert normalize_debt_to_equity(1.35) == 1.35


def test_compute_peg():
    assert compute_peg(15, 0.20) == 0.75
    assert compute_peg(9, 0.15) == 0.6


def test_base_screen_passes_ideal_candidate():
    passed, checks, fail = apply_base_screen(_ideal_metrics())
    assert passed is True
    assert fail is None
    assert lynch_score(checks) == 100.0


def test_anti_filter_rejects_negative_earnings():
    passed, _, fail = apply_anti_filters(_ideal_metrics(trailing_eps=-1.0, pe_ratio=None))
    assert passed is False
    assert fail == "no_earnings"


def test_fast_grower_classification():
    ok, _ = classify_fast_grower(_ideal_metrics())
    assert ok is True


def test_stalwart_classification():
    metrics = _ideal_metrics(
        market_cap=50_000_000_000,
        pe_ratio=18.0,
        eps_growth_5y=0.12,
        eps_growth_for_peg=0.12,
        dividend_yield=0.02,
    )
    ok, checks = classify_stalwart(metrics)
    assert ok is True
    assert len(checks) == 4


def test_asset_play_classification():
    metrics = _ideal_metrics(
        price_to_book=0.7,
        net_cash_price_ratio=0.35,
    )
    ok, checks = classify_asset_play(metrics)
    assert ok is True
    assert len(checks) == 2


def test_assign_categories_multiple():
    metrics = _ideal_metrics(
        market_cap=2_000_000_000,
        eps_growth_5y=0.22,
        price_to_book=0.7,
        net_cash_price_ratio=0.4,
    )
    cats, checks = assign_categories(metrics)
    assert "fast_grower" in cats
    assert "asset_play" in cats
    assert len(checks) == 6


def test_summary_category_only_pass_scores_category_checks():
    """Category passers should not inherit failed base-screen checks in lynch_score."""
    metrics = _ideal_metrics(
        ticker="CAT",
        institutional_ownership=0.80,
        analyst_count=15,
        insider_purchases_6m=0,
        shares_outstanding_change_yoy=0.01,
    )
    base_ok, _, _ = apply_base_screen(metrics)
    assert base_ok is False

    runner = LynchScannerRunner(
        universe=["CAT"],
        preset="summary",
        output=Path("unused.csv"),
        report=None,
    )
    detail = runner._evaluate(metrics)
    assert detail["passed"] is True
    assert "fast_grower" in detail["categories"]
    assert detail["lynch_score"] == 100.0


def test_lynch_score_empty_checks_returns_none():
    assert lynch_score([]) is None


def test_runner_fetch_failed_marks_score_unavailable(monkeypatch, tmp_path):
    output = tmp_path / "lynch.csv"
    runner = LynchScannerRunner(
        universe=["BAD"],
        preset="summary",
        output=output,
        report=None,
    )
    monkeypatch.setattr(
        "quant_hub.lynch.runner.fetch_lynch_metrics_batch",
        lambda _: [{"ticker": "BAD", "error": "fetch_failed"}],
    )
    df, report = runner.run()
    assert df.iloc[0]["lynch_score"] is None or pd.isna(df.iloc[0]["lynch_score"])
    assert report["tickers"][0]["lynch_score"] is None
    assert report["scan_summary"]["metrics_quality"]["fetch_errors"] == 1


def test_runner_evaluate_summary_preset(monkeypatch, tmp_path):
    metrics = _ideal_metrics(ticker="LYNCH")
    output = tmp_path / "lynch.csv"
    runner = LynchScannerRunner(
        universe=["LYNCH"],
        preset="summary",
        output=output,
        report=None,
    )
    monkeypatch.setattr(
        "quant_hub.lynch.runner.fetch_lynch_metrics_batch",
        lambda _: [metrics],
    )
    df, report = runner.run()
    assert len(df) == 1
    assert bool(df.iloc[0]["passed"]) is True
    assert report["scan_summary"]["passed_count"] == 1
    assert len(report["candidates"]) == 1


def test_base_screen_passes_with_manageable_debt_not_net_cash():
    passed, _, fail = apply_base_screen(
        _ideal_metrics(net_cash=-100_000_000, debt_to_equity=0.25, eps_growth_for_peg=0.18)
    )
    assert passed is True
    assert fail is None


def test_missing_coverage_fails_base_screen():
    passed, checks, fail = apply_base_screen(
        _ideal_metrics(
            institutional_ownership=None,
            analyst_count=None,
            insider_purchases_6m=None,
            shares_outstanding_change_yoy=None,
        )
    )
    assert passed is False
    assert fail in ("wall_street_neglect", "insider_or_buyback")
    neglect = next(c for c in checks if c["rule"] == "wall_street_neglect")
    assert neglect["passed"] is False


def test_enrich_checks_adds_plain_language():
    from quant_hub.lynch.explain import enrich_checks

    metrics = _ideal_metrics()
    _, checks, _ = apply_base_screen(metrics)
    enriched = enrich_checks(checks, metrics)
    assert enriched[0].get("result_text", "").startswith(("✓", "✗"))
    assert enriched[0].get("why_it_matters")


def test_build_lynch_email_includes_candidates():
    report = {
        "universe_id": "sp500_index",
        "scan_summary": {
            "preset_label": "Full Lynch Scan",
            "universe_size": 10,
            "passed_count": 1,
            "category_counts": {"fast_grower": 1, "stalwart": 0, "asset_play": 0},
        },
        "candidates": [
            {
                "ticker": "ACME",
                "company_name": "Acme Corp",
                "categories": ["fast_grower"],
                "lynch_score": 85.0,
                "pe_ratio": 14.0,
                "peg_ratio": 0.7,
                "eps_growth_5y_pct": 22.0,
                "market_cap": 2_000_000_000,
                "tier_reason": "Lynch match: Fast Grower",
                "investor_summary": "ACME (Acme Corp) trades at 14× trailing earnings with 22% growth.",
            }
        ],
        "qualitative_overlay": ["Is the business easy to understand?"],
    }
    subject, html = build_lynch_email(report)
    assert "ACME" in subject or "1 name" in subject
    assert "ACME" in html
    assert "Fast Grower" in html
    assert "Before you buy" in html
