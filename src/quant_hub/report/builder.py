from quant_hub.report.launchpad_diagnostics import launchpad_score_components_detail
from quant_hub.scoring.launchpad import FILTER_LABELS as LAUNCHPAD_FILTER_LABELS
from quant_hub.scoring.launchpad import launchpad_eligibility_detail
from quant_hub.strategies.launchpad.tiers import explain_tier as explain_launchpad_tier


def _explain_tier(row: dict, strategy_id: str) -> str:
    if not row.get("eligible"):
        reason = row.get("filter_reason", "unknown")
        return LAUNCHPAD_FILTER_LABELS.get(reason, reason)

    if strategy_id == "launchpad":
        return explain_launchpad_tier(row)

    tier = row.get("tier", "")
    final = row.get("final_adjusted_score", 0)
    return f"{tier}: final score {final:.1f}"


def _tier_counts(results_df, strategy_id: str) -> dict:
    _ = strategy_id
    return {
        "Tier 1": int((results_df["tier"] == "Tier 1").sum()),
        "Tier 2": int((results_df["tier"] == "Tier 2").sum()),
        "Tier 3": int((results_df["tier"] == "Tier 3").sum()),
        "filtered": int((results_df["tier"] == "filtered").sum()),
    }


def _actionable_count(tier_counts: dict, strategy_id: str) -> int:
    _ = strategy_id
    return tier_counts.get("Tier 1", 0) + tier_counts.get("Tier 2", 0)


def explain_tier(row: dict) -> str:
    """Launchpad tier explanation."""
    return _explain_tier(row, "launchpad")


def build_ticker_report(
    *,
    ticker: str,
    row: dict,
    stock_df,
    spy_df,
    sector_df,
    sector_etf: str | None,
    fund: dict,
    scores: dict | None,
    strategy_id: str = "launchpad",
    eligibility_mode: str = "stock",
) -> dict:
    _ = sector_df, fund, eligibility_mode
    if stock_df is None or stock_df.empty:
        eligibility = {
            "passed": False,
            "fail_reason": "no_price_data",
            "checks": [],
            "summary": LAUNCHPAD_FILTER_LABELS["no_price_data"],
        }
        return {
            "ticker": ticker,
            "verdict": "excluded",
            "eligible": False,
            "tier": "filtered",
            "tier_reason": LAUNCHPAD_FILTER_LABELS["no_price_data"],
            "eligibility": eligibility,
            "scores": None,
            "summary": {
                "raw_score": 0,
                "normalized_score": 0,
                "final_adjusted_score": 0,
            },
        }

    elig = launchpad_eligibility_detail(stock_df)
    elig["summary"] = (
        "Passed all eligibility filters"
        if elig["passed"]
        else LAUNCHPAD_FILTER_LABELS.get(elig["fail_reason"], elig["fail_reason"])
    )

    if not elig["passed"]:
        return {
            "ticker": ticker,
            "verdict": "excluded",
            "eligible": False,
            "tier": "filtered",
            "tier_reason": elig["summary"],
            "eligibility": elig,
            "scores": None,
            "summary": {
                "raw_score": 0,
                "normalized_score": 0,
                "final_adjusted_score": 0,
            },
        }

    score_detail = launchpad_score_components_detail(
        stock_df=stock_df,
        scores=scores or {},
        spy_df=spy_df,
    )

    return {
        "ticker": ticker,
        "verdict": "eligible",
        "eligible": True,
        "tier": row.get("tier"),
        "tier_reason": _explain_tier(row, strategy_id),
        "sector_etf": sector_etf,
        "eligibility": elig,
        "scores": score_detail,
        "summary": {
            "raw_score": row.get("raw_score"),
            "normalized_score": round(row.get("normalized_score", 0), 2),
            "regime_multiplier": row.get("regime_multiplier"),
            "final_adjusted_score": round(row.get("final_adjusted_score", 0), 2),
        },
    }


def build_scan_report(
    *,
    results_df,
    universe: list[str],
    stock_dfs: dict,
    spy_df,
    sector_dfs: dict,
    sector_etfs: dict,
    fund_map: dict,
    regime_detail: dict,
    scores_by_ticker: dict,
    strategy_id: str = "launchpad",
    fundamentals_quality: dict | None = None,
    eligibility_mode: str = "stock",
    data_provenance: dict | None = None,
) -> dict:
    _ = fundamentals_quality, eligibility_mode
    tickers_report = []
    for ticker in universe:
        row = results_df[results_df["ticker"] == ticker].iloc[0].to_dict()
        sector_etf = sector_etfs.get(ticker)
        sector_df = sector_dfs.get(sector_etf)
        tickers_report.append(
            build_ticker_report(
                ticker=ticker,
                row=row,
                stock_df=stock_dfs.get(ticker),
                spy_df=spy_df,
                sector_df=sector_df,
                sector_etf=sector_etf,
                fund=fund_map.get(ticker, {}),
                scores=scores_by_ticker.get(ticker),
                strategy_id=strategy_id,
            )
        )

    eligible = [t for t in tickers_report if t["eligible"]]
    excluded = [t for t in tickers_report if not t["eligible"]]

    filter_counts: dict[str, int] = {}
    for t in excluded:
        reason = t["eligibility"].get("fail_reason", "unknown")
        filter_counts[reason] = filter_counts.get(reason, 0) + 1

    tier_counts = _tier_counts(results_df, strategy_id)

    summary = {
        "universe_size": len(universe),
        "eligible_count": len(eligible),
        "excluded_count": len(excluded),
        "tier_counts": tier_counts,
        "actionable_count": _actionable_count(tier_counts, strategy_id),
        "filter_breakdown": filter_counts,
    }

    report = {
        "strategy_id": strategy_id,
        "scan_summary": summary,
        "market_regime": regime_detail,
        "tickers": tickers_report,
    }
    if data_provenance:
        report["data_provenance"] = data_provenance
    return report
