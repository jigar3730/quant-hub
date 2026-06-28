"""Peter Lynch scanner pipeline."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from quant_hub.lynch import config as lynch_cfg
from quant_hub.lynch.categories import (
    QUALITATIVE_OVERLAY,
    assign_categories,
    classify_asset_play,
    classify_fast_grower,
    classify_stalwart,
)
from quant_hub.lynch.explain import build_fundamental_snapshot, build_investor_summary, enrich_checks
from quant_hub.lynch.filters import apply_anti_filters, apply_base_screen, lynch_score
from quant_hub.lynch.metrics import fetch_lynch_metrics_batch
from quant_hub.lynch.report import export_json, export_markdown
from quant_hub.data.provenance import build_data_provenance
from quant_hub.data.quality import lynch_metrics_quality_summary

logger = logging.getLogger(__name__)


class LynchScannerRunner:
    def __init__(
        self,
        *,
        universe: list[str],
        preset: str = "summary",
        output: Path,
        report: str | None = "both",
        report_json: Path | None = None,
        report_md: Path | None = None,
        universe_id: str = "sp500",
    ) -> None:
        if preset not in lynch_cfg.PRESETS:
            raise ValueError(f"Unknown preset: {preset}")
        self.universe = universe
        self.preset = preset
        self.output = output
        self.report = report
        self.report_json = report_json
        self.report_md = report_md
        self.universe_id = universe_id

    def run(self) -> tuple[pd.DataFrame, dict]:
        logger.info(
            "Lynch scan: %d tickers, preset=%s, universe=%s",
            len(self.universe),
            self.preset,
            self.universe_id,
        )

        metrics_list = fetch_lynch_metrics_batch(self.universe)
        metrics_quality = lynch_metrics_quality_summary(metrics_list)
        rows: list[dict] = []
        candidates: list[dict] = []

        for metrics in metrics_list:
            detail = self._evaluate(metrics)
            rows.append(detail)
            if detail["passed"]:
                candidates.append(detail)

        df = pd.DataFrame([_csv_row(r) for r in rows])
        if not df.empty:
            df = df.sort_values(
                ["passed", "lynch_score", "peg_ratio"],
                ascending=[False, False, True],
                na_position="last",
            )

        self.output.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(self.output, index=False)
        logger.info("Wrote %d rows to %s", len(df), self.output)

        scan_report = self._build_report(self.universe, rows, candidates, metrics_quality)

        if self.report and self.report_json:
            if self.report in ("json", "both"):
                export_json(scan_report, self.report_json)
                logger.info("Wrote Lynch JSON report to %s", self.report_json)
            if self.report in ("md", "both") and self.report_md:
                export_markdown(scan_report, self.report_md)
                logger.info("Wrote Lynch markdown summary to %s", self.report_md)

        return df, scan_report

    def _evaluate(self, metrics: dict) -> dict:
        ticker = metrics.get("ticker", "?")
        if metrics.get("error"):
            return _fetch_failed_detail(ticker, metrics)

        anti_ok, anti_checks, anti_fail = apply_anti_filters(metrics)
        all_checks = list(anti_checks)

        passed = False
        fail_reason = anti_fail
        categories: list[str] = []

        if anti_ok:
            if self.preset == "fast_grower":
                passed, preset_checks = classify_fast_grower(metrics)
                all_checks.extend(preset_checks)
                if passed:
                    categories = ["fast_grower"]
                else:
                    fail_reason = "fast_grower_criteria"
            elif self.preset == "stalwart":
                passed, preset_checks = classify_stalwart(metrics)
                all_checks.extend(preset_checks)
                if passed:
                    categories = ["stalwart"]
                else:
                    fail_reason = "stalwart_criteria"
            elif self.preset == "asset_play":
                passed, preset_checks = classify_asset_play(metrics)
                all_checks.extend(preset_checks)
                if passed:
                    categories = ["asset_play"]
                else:
                    fail_reason = "asset_play_criteria"
            elif self.preset == "base":
                passed, base_checks, fail_reason = apply_base_screen(metrics)
                all_checks.extend(base_checks)
            else:
                base_ok, base_checks, base_fail = apply_base_screen(metrics)
                all_checks.extend(base_checks)
                categories = assign_categories(metrics)
                passed = base_ok or bool(categories)
                fail_reason = None if passed else (base_fail or "no_category_match")

        m = metrics
        score = lynch_score(all_checks)
        all_checks = enrich_checks(all_checks, m)
        investor_summary = build_investor_summary(
            m, all_checks, passed=passed, categories=categories
        )
        fundamental_snapshot = build_fundamental_snapshot(m)
        primary_tier = categories[0] if categories else ("passed" if passed else "filtered")

        return {
            "ticker": ticker,
            "company_name": m.get("company_name"),
            "sector": m.get("sector"),
            "sector_etf": None,
            "passed": passed,
            "eligible": passed,
            "preset": self.preset,
            "categories": categories,
            "lynch_score": score,
            "fail_reason": fail_reason or "",
            "tier_reason": _tier_reason(passed, categories, m, all_checks),
            "investor_summary": investor_summary,
            "fundamental_snapshot": fundamental_snapshot,
            "tier": primary_tier,
            "pe_ratio": m.get("pe_ratio"),
            "peg_ratio": m.get("peg_ratio"),
            "eps_growth_5y_pct": _to_pct(m.get("eps_growth_5y")),
            "eps_growth_ttm_pct": _to_pct(m.get("eps_growth_ttm")),
            "debt_to_equity": m.get("debt_to_equity"),
            "institutional_pct": _to_pct(m.get("institutional_ownership")),
            "analyst_count": m.get("analyst_count"),
            "market_cap": m.get("market_cap"),
            "dividend_yield": m.get("dividend_yield"),
            "price_to_book": m.get("price_to_book"),
            "net_cash": m.get("net_cash"),
            "metrics": m,
            "checks": all_checks,
            "summary": {
                "final_adjusted_score": score,
                "normalized_score": score,
                "raw_score": score,
            },
            "eligibility": {
                "passed": passed,
                "fail_reason": fail_reason,
            },
        }

    def _build_report(
        self,
        universe: list[str],
        rows: list[dict],
        candidates: list[dict],
        metrics_quality: dict,
    ) -> dict:
        cat_counts = {
            "fast_grower": sum(1 for r in rows if "fast_grower" in r.get("categories", [])),
            "stalwart": sum(1 for r in rows if "stalwart" in r.get("categories", [])),
            "asset_play": sum(1 for r in rows if "asset_play" in r.get("categories", [])),
        }
        passed_count = sum(1 for r in rows if r["passed"])
        sorted_candidates = sorted(
            candidates,
            key=lambda r: (r.get("lynch_score") or 0, -(r.get("peg_ratio") or 99)),
            reverse=True,
        )
        return {
            "strategy_id": "lynch",
            "universe_id": self.universe_id,
            "scan_summary": {
                "scanner": "peter_lynch",
                "preset": self.preset,
                "preset_label": lynch_cfg.PRESET_LABELS[self.preset],
                "universe_size": len(universe),
                "passed_count": passed_count,
                "category_counts": cat_counts,
                "actionable_count": passed_count,
                "eligible_count": passed_count,
                "excluded_count": len(universe) - passed_count,
                "tier_counts": {
                    "fast_grower": cat_counts["fast_grower"],
                    "stalwart": cat_counts["stalwart"],
                    "asset_play": cat_counts["asset_play"],
                    "filtered": len(universe) - passed_count,
                },
                "metrics_quality": metrics_quality,
            },
            "market_regime": {
                "label": "fundamental",
                "multiplier": 1.0,
                "preset": self.preset,
            },
            "data_provenance": build_data_provenance(
                strategy_id="lynch",
                universe_id=self.universe_id,
                price_source="yfinance",
                price_cache="live",
                fundamentals_cache="live",
                extra={"preset": self.preset},
            ),
            "qualitative_overlay": QUALITATIVE_OVERLAY,
            "tickers": rows,
            "candidates": sorted_candidates,
        }


def _fetch_failed_detail(ticker: str, metrics: dict) -> dict:
    err = metrics.get("error", "fetch_failed")
    reason = (
        "Yahoo Finance data fetch failed — Lynch score unavailable. "
        "Re-run the scan; scores of 0 here are not real failures."
    )
    return {
        "ticker": ticker,
        "company_name": None,
        "sector": None,
        "sector_etf": None,
        "passed": False,
        "eligible": False,
        "preset": "",
        "categories": [],
        "lynch_score": None,
        "fail_reason": err,
        "tier_reason": reason,
        "investor_summary": reason,
        "fundamental_snapshot": [],
        "tier": "filtered",
        "pe_ratio": None,
        "peg_ratio": None,
        "eps_growth_5y_pct": None,
        "eps_growth_ttm_pct": None,
        "debt_to_equity": None,
        "institutional_pct": None,
        "analyst_count": None,
        "market_cap": None,
        "dividend_yield": None,
        "price_to_book": None,
        "net_cash": None,
        "metrics": metrics,
        "checks": [],
        "summary": {
            "final_adjusted_score": None,
            "normalized_score": None,
            "raw_score": None,
        },
        "eligibility": {
            "passed": False,
            "fail_reason": err,
        },
    }


def _csv_row(detail: dict) -> dict:
    return {
        "ticker": detail["ticker"],
        "company_name": detail.get("company_name"),
        "sector": detail.get("sector"),
        "passed": detail["passed"],
        "categories": ",".join(detail.get("categories", [])),
        "lynch_score": detail["lynch_score"],
        "fail_reason": detail.get("fail_reason"),
        "tier_reason": detail.get("tier_reason"),
        "pe_ratio": detail.get("pe_ratio"),
        "peg_ratio": detail.get("peg_ratio"),
        "eps_growth_5y_pct": detail.get("eps_growth_5y_pct"),
        "debt_to_equity": detail.get("debt_to_equity"),
        "institutional_pct": detail.get("institutional_pct"),
        "analyst_count": detail.get("analyst_count"),
        "market_cap": detail.get("market_cap"),
        "dividend_yield": detail.get("dividend_yield"),
        "price_to_book": detail.get("price_to_book"),
        "net_cash": detail.get("net_cash"),
    }


def _to_pct(value) -> float | None:
    if value is None:
        return None
    v = float(value)
    return round(v * 100, 2) if abs(v) <= 1.5 else round(v, 2)


def _tier_reason(
    passed: bool,
    categories: list[str],
    metrics: dict,
    checks: list[dict] | None = None,
) -> str:
    if not passed:
        failed = [c for c in (checks or []) if not c.get("passed")]
        if failed:
            return failed[0].get("result_text") or "Did not pass Lynch quantitative screen"
        return "Did not pass Lynch quantitative screen"
    if categories:
        labels = ", ".join(c.replace("_", " ").title() for c in categories)
        peg = metrics.get("peg_ratio")
        if peg is not None and peg < lynch_cfg.PEG_BARGAIN:
            return f"Lynch {labels}; exceptional PEG bargain ({peg:.2f})"
        return f"Lynch match: {labels} — see investor summary for details."
    peg = metrics.get("peg_ratio")
    if peg is not None and peg < lynch_cfg.PEG_BARGAIN:
        return f"Base screen pass; exceptional PEG bargain ({peg:.2f})"
    return "Passes Lynch base quantitative screen — growth at a reasonable price."
