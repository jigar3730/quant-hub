"""Report dict (shaped for ``ScanRepository.upsert_scan``) and markdown summary.

Only ``market_regime``, ``filter_breakdown``/counts and each ticker's ``detail`` survive the
Postgres round trip into the API (``_build_report_dict`` rebuilds the rest), so the fields the UIs
need (as-of date, freshness, regime gate, schema version) are denormalised into those.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from quant_hub.data.provenance import build_data_provenance
from quant_hub.sector_swing import config as C
from quant_hub.sector_swing.config import SwingParams
from quant_hub.sector_swing.models import TickerOutcome

if TYPE_CHECKING:
    from quant_hub.sector_swing.runner import ScanResult

_TIER_ORDER = {tier: i for i, tier in enumerate(C.TIERS)}

_REASON_TEXT = {
    C.REASON_NO_PRICE_DATA: "No price data returned",
    C.REASON_INSUFFICIENT_HISTORY: "Not enough daily history",
    C.REASON_DATA_QUALITY: "Failed price data-quality checks",
    C.REASON_ILLIQUID: "Below dollar-volume / price floor",
    C.REASON_NOT_LEADER: "Not a relative-strength leader vs SPY",
    C.REASON_TREND_FAIL: "Leader, but trend filter failed",
    C.REASON_STOP_TOO_WIDE: "Setup valid but stop is too wide for the ATR cap",
    C.REASON_CORRELATED: "Too correlated with a higher-ranked plan in this scan",
    C.REASON_SIZE_ZERO: "Stop distance leaves zero shares at the risk budget",
    C.REASON_SIGNAL_CAP: "Qualified, but the per-scan new-signal cap was reached",
    C.REASON_COMPUTE_ERROR: "Computation error (see detail.error)",
}


def _summary_text(o: TickerOutcome) -> str:
    if o.tier == C.TIER_TRIGGER and o.plan:
        return (
            f"Trigger: pullback turned up. Plan {o.plan.shares} sh, entry ref "
            f"{o.plan.entry_ref:.2f}, stop {o.plan.stop:.2f}, 2R target {o.plan.target_2r:.2f}"
        )
    if o.tier == C.TIER_WATCH and o.regime_blocked:
        return "Setup qualifies but the SPY regime gate is off; levels are informational only"
    if o.tier == C.TIER_WATCH:
        return "Leader in trend; pullback in progress, no trigger yet"
    if o.tier == C.TIER_EXTENDED:
        return "Leader in trend; no pullback yet (extended)"
    return _REASON_TEXT.get(o.reason or "", o.reason or "Filtered")


def _pct(value: float | None) -> float | None:
    return None if value is None else round(value * 100.0, 4)


def outcome_to_detail(o: TickerOutcome, *, as_of_price: str) -> dict[str, Any]:
    eligible = o.tier != C.TIER_FILTERED
    rs = None if o.rs_score_pct is None else round(o.rs_score_pct, 4)
    detail: dict[str, Any] = {
        "schema_version": C.SCHEMA_VERSION,
        "ticker": o.ticker,
        "eligible": eligible,
        "tier": o.tier,
        "sector_etf": C.SECTOR_ETF_COLUMN,
        "as_of_price": as_of_price,
        "regime_blocked": bool(o.regime_blocked),
        "summary": {
            "final_adjusted_score": rs,
            "rs_score_pct": rs,
            "rs_rank": o.rs_rank,
            "ret_63d_pct": _pct(o.indicators.ret_short) if o.indicators else None,
            "ret_126d_pct": _pct(o.indicators.ret_long) if o.indicators else None,
        },
        "eligibility": {
            "passed": eligible,
            "fail_reason": o.reason if not eligible else None,
            "summary": _summary_text(o),
            "checks": [c.to_dict() for c in o.checks],
        },
    }
    if o.indicators:
        ind = o.indicators
        detail["indicators"] = {
            "bar_date": str(ind.bar_date),
            "close": round(ind.close, 4),
            "ema10": round(ind.ema10, 4),
            "ema20": round(ind.ema20, 4),
            "sma50": round(ind.sma50, 4),
            "atr14": round(ind.atr14, 4),
            "adx14": round(ind.adx14, 4),
            "pullback_low": round(ind.pullback_low, 4),
            "avg_dollar_volume": round(ind.avg_dollar_volume, 0),
        }
    if o.plan:
        detail["trade_plan"] = o.plan.to_dict()
    if o.error:
        detail["error"] = o.error
    return detail


def build_report(
    result: ScanResult,
    *,
    universe: list[str],
    universe_id: str,
    params: SwingParams,
    equity: float,
    risk_pct: float,
    data_freshness: str,
    expected_session: date | None,
    scan_date: date,
    price_cache: str,
    dry_run: bool,
) -> dict[str, Any]:
    as_of = str(result.spy_as_of)
    ordered = sorted(
        result.outcomes,
        key=lambda o: (_TIER_ORDER[o.tier], o.rs_rank if o.rs_rank else 10**6, o.ticker),
    )
    tier_counts = {tier: 0 for tier in C.TIERS}
    filter_breakdown: dict[str, int] = {}
    for o in ordered:
        tier_counts[o.tier] += 1
        if o.tier == C.TIER_FILTERED and o.reason:
            filter_breakdown[o.reason] = filter_breakdown.get(o.reason, 0) + 1

    failed = filter_breakdown.get(C.REASON_NO_PRICE_DATA, 0)
    eligible = len(ordered) - tier_counts[C.TIER_FILTERED]

    regime = dict(result.regime)
    regime.update(
        {
            "regime_gate_passed": bool(result.regime_gate_passed),
            "gate_rule": f"SPY > SMA{params.regime_fast_sma} and > SMA{params.regime_slow_sma}",
            "as_of_price": as_of,
            "data_freshness": data_freshness,
            "schema_version": C.SCHEMA_VERSION,
        }
    )

    extra: dict[str, Any] = {
        "schema_version": C.SCHEMA_VERSION,
        "equity_assumed": equity,
        "risk_pct": risk_pct,
        "max_position_pct": params.max_position_pct,
        "expected_session": str(expected_session) if expected_session else None,
        "data_freshness": data_freshness,
        "config_hash": C.params_hash(params),
    }
    if dry_run:
        extra["dry_run"] = True

    return {
        "strategy_id": C.STRATEGY_ID,
        "universe_id": universe_id,
        "scan_date": str(scan_date),
        "scan_time": datetime.now(UTC).isoformat(),
        "scan_summary": {
            "scanner": C.STRATEGY_ID,
            "universe_size": len(universe),
            "eligible_count": eligible,
            "excluded_count": tier_counts[C.TIER_FILTERED],
            "tier_counts": tier_counts,
            "actionable_count": tier_counts[C.TIER_TRIGGER],
            "filter_breakdown": filter_breakdown,
            "tickers_fetched": len(ordered) - failed,
            "tickers_failed": failed,
        },
        "market_regime": regime,
        "data_provenance": build_data_provenance(
            strategy_id=C.STRATEGY_ID,
            universe_id=universe_id,
            scan_date=scan_date,
            price_cache=price_cache,
            as_of_price=as_of,
            extra=extra,
        ),
        "tickers": [outcome_to_detail(o, as_of_price=as_of) for o in ordered],
    }


def outcomes_to_dataframe(outcomes: list[TickerOutcome]) -> pd.DataFrame:
    rows = []
    for o in sorted(
        outcomes, key=lambda o: (_TIER_ORDER[o.tier], o.rs_rank if o.rs_rank else 10**6, o.ticker)
    ):
        plan = o.plan
        rows.append(
            {
                "ticker": o.ticker,
                "tier": o.tier,
                "rs_rank": o.rs_rank,
                "rs_score_pct": None if o.rs_score_pct is None else round(o.rs_score_pct, 4),
                "filter_reason": o.reason if o.tier == C.TIER_FILTERED else None,
                "regime_blocked": o.regime_blocked,
                "entry_ref": plan.entry_ref if plan else None,
                "stop": plan.stop if plan else None,
                "target_2r": plan.target_2r if plan else None,
                "chase_limit": plan.chase_limit if plan else None,
                "shares": plan.shares if plan else None,
                "risk_dollars": plan.risk_dollars if plan else None,
            }
        )
    return pd.DataFrame(rows)


def render_markdown(report: dict[str, Any]) -> str:
    regime = report["market_regime"]
    summary = report["scan_summary"]
    prov = report.get("data_provenance", {})
    counts = summary["tier_counts"]
    lines = [
        f"# Sector ETF swing scan — {report['scan_date']}",
        "",
        f"- Price data as of **{regime.get('as_of_price')}** "
        f"(freshness: {regime.get('data_freshness')})",
        f"- Regime gate ({regime.get('gate_rule')}): "
        f"**{'PASS' if regime.get('regime_gate_passed') else 'FAIL — no new trade plans'}** "
        f"(SPY {regime.get('spy_price')}, SMA50 {regime.get('sma50')}, "
        f"SMA200 {regime.get('sma200')})",
        f"- Trigger {counts[C.TIER_TRIGGER]} · Watch {counts[C.TIER_WATCH]} · "
        f"Extended {counts[C.TIER_EXTENDED]} · Filtered {counts[C.TIER_FILTERED]}",
        f"- Sizing assumption: equity ${prov.get('equity_assumed', 0):,.0f}, "
        f"{prov.get('risk_pct', 0):.2%} risk per trade (placeholders unless configured)",
        "",
    ]
    tickers = report["tickers"]

    plans = [t for t in tickers if t["tier"] == C.TIER_TRIGGER and t.get("trade_plan")]
    lines += ["## Trade plans (Tier 1)", ""]
    if plans:
        lines += [
            "| ETF | RS rank | Entry ref | Stop | 2R target | Chase limit | Shares | Risk $ |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for t in plans:
            p = t["trade_plan"]
            lines.append(
                f"| {t['ticker']} | {t['summary']['rs_rank']} | {p['entry_ref']:.2f} | "
                f"{p['stop']:.2f} | {p['target_2r']:.2f} | {p['chase_limit']:.2f} | "
                f"{p['shares']} | {p['risk_dollars']:,.0f} |"
            )
        lines += [
            "",
            "Skip a plan if the open is above its chase limit or at/below its stop. "
            "Levels use adjusted history; confirm against a live quote.",
        ]
    else:
        lines.append("_No trigger setups._")

    watch = [t for t in tickers if t["tier"] == C.TIER_WATCH]
    lines += ["", "## Watchlist (Tier 2)", ""]
    lines += (
        [f"- **{t['ticker']}** (RS #{t['summary']['rs_rank']}): {t['eligibility']['summary']}"
         for t in watch]
        or ["_None._"]
    )

    extended = [t for t in tickers if t["tier"] == C.TIER_EXTENDED]
    lines += ["", "## Extended (Tier 3)", ""]
    lines += [f"- **{t['ticker']}** (RS #{t['summary']['rs_rank']})" for t in extended] or ["_None._"]

    lines += ["", "## Filtered", ""]
    breakdown = summary["filter_breakdown"]
    lines += [f"- {reason}: {n}" for reason, n in sorted(breakdown.items())] or ["_None._"]
    lines += ["", "_Research tool only — not investment advice and not a trading bot._", ""]
    return "\n".join(lines)


def write_markdown(report: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report))
    return path
