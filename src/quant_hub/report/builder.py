from quant_hub.filters.eligibility import FILTER_LABELS, eligibility_detail
from quant_hub.report.diagnostics import score_components_detail
from quant_hub.strategies.breakout.tiers import explain_tier as explain_breakout_tier


def _factor_scores_detail(scores: dict) -> dict:
    detail = {}
    for key, val in scores.items():
        if not key.endswith("_score"):
            continue
        name = key[:-6]
        detail[name] = {
            "score": round(float(val), 2),
            "max": 0,
            "meaning": f"{name.replace('_', ' ').title()} component score",
        }
    return detail


def _explain_tier(row: dict, strategy_id: str) -> str:
    if not row.get("eligible"):
        reason = row.get("filter_reason", "unknown")
        return FILTER_LABELS.get(reason, reason)

    if strategy_id == "swing":
        tier = row.get("tier", "")
        final = row.get("final_adjusted_score", 0)
        if tier == "A":
            return f"Strong pullback setup: final score {final:.1f} (>=80)"
        if tier == "B":
            return f"Actionable pullback: final score {final:.1f} (65-79)"
        return f"Lower conviction setup: final score {final:.1f} (<65)"

    return explain_breakout_tier(row)


def _tier_counts(results_df, strategy_id: str) -> dict:
    if strategy_id == "swing":
        return {
            "A": int((results_df["tier"] == "A").sum()),
            "B": int((results_df["tier"] == "B").sum()),
            "C": int((results_df["tier"] == "C").sum()),
            "filtered": int((results_df["tier"] == "filtered").sum()),
        }
    return {
        "Tier 1": int((results_df["tier"] == "Tier 1").sum()),
        "Tier 2": int((results_df["tier"] == "Tier 2").sum()),
        "Tier 3": int((results_df["tier"] == "Tier 3").sum()),
        "filtered": int((results_df["tier"] == "filtered").sum()),
    }


def _actionable_count(tier_counts: dict, strategy_id: str) -> int:
    if strategy_id == "swing":
        return tier_counts.get("A", 0) + tier_counts.get("B", 0)
    return tier_counts.get("Tier 1", 0) + tier_counts.get("Tier 2", 0)


def explain_tier(row: dict) -> str:
    """Breakout tier explanation (legacy export for tests and callers)."""
    return _explain_tier(row, "breakout")


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
    strategy_id: str = "breakout",
) -> dict:
    if stock_df is None or stock_df.empty:
        eligibility = {
            "passed": False,
            "fail_reason": "no_price_data",
            "checks": [],
            "summary": FILTER_LABELS["no_price_data"],
        }
        return {
            "ticker": ticker,
            "verdict": "excluded",
            "eligible": False,
            "tier": "filtered",
            "tier_reason": FILTER_LABELS["no_price_data"],
            "eligibility": eligibility,
            "scores": None,
            "summary": {
                "raw_score": 0,
                "normalized_score": 0,
                "final_adjusted_score": 0,
            },
        }

    elig = eligibility_detail(stock_df)
    elig["summary"] = (
        "Passed all eligibility filters"
        if elig["passed"]
        else FILTER_LABELS.get(elig["fail_reason"], elig["fail_reason"])
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

    score_detail = (
        _factor_scores_detail(scores or {})
        if strategy_id == "swing"
        else score_components_detail(
            stock_df=stock_df,
            spy_df=spy_df,
            sector_df=sector_df,
            sector_etf=sector_etf,
            fund=fund,
            scores=scores or {},
        )
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
    strategy_id: str = "breakout",
) -> dict:
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

    return {
        "strategy_id": strategy_id,
        "scan_summary": {
            "universe_size": len(universe),
            "eligible_count": len(eligible),
            "excluded_count": len(excluded),
            "tier_counts": tier_counts,
            "actionable_count": _actionable_count(tier_counts, strategy_id),
            "filter_breakdown": filter_counts,
        },
        "market_regime": regime_detail,
        "tickers": tickers_report,
    }
