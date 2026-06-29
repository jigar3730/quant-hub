"""Build daily and weekly digest payloads from Postgres scan data."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from quant_hub.config import OUTPUT_DIR
from quant_hub.digest import policy as P
from quant_hub.infrastructure.postgres.repository import ScanRepository

DIGEST_OUTPUT_DIR = OUTPUT_DIR / "digest"


def _ticker_row(t: dict) -> dict[str, Any]:
    summary = t.get("summary") or {}
    return {
        "ticker": t["ticker"],
        "tier": t.get("tier"),
        "final_score": summary.get("final_adjusted_score") or t.get("final_score"),
        "normalized_score": summary.get("normalized_score"),
        "sector_etf": t.get("sector_etf"),
        "tier_reason": t.get("tier_reason"),
    }


def _swing_row(t: dict) -> dict[str, Any]:
    setup = t.get("setup_detail") or {}
    summary = t.get("summary") or {}
    score = setup.get("swing_score") or summary.get("swing_score")
    return {
        "ticker": t["ticker"],
        "tier": t.get("tier"),
        "swing_score": score,
        "quality_label": setup.get("quality_label"),
        "rsi": setup.get("rsi") or summary.get("rsi"),
        "close": setup.get("close"),
    }


def _lynch_row(t: dict) -> dict[str, Any]:
    return {
        "ticker": t["ticker"],
        "lynch_score": t.get("lynch_score"),
        "categories": t.get("categories") or [],
        "pe_ratio": t.get("pe_ratio"),
        "peg_ratio": t.get("peg_ratio"),
        "company_name": t.get("company_name"),
        "tier_reason": t.get("tier_reason"),
    }


def _is_swing_quality(t: dict) -> bool:
    setup = t.get("setup_detail") or {}
    score = setup.get("swing_score")
    if score is not None and float(score) >= P.WEEKLY_SWING_MIN_SCORE:
        return True
    label = (setup.get("quality_label") or "").upper()
    return label.startswith("A") or label.startswith("B")


def get_previous_scan_date(repo: ScanRepository, *, scan_date: date, strategy_id: str, universe_id: str) -> date | None:
    runs = repo.list_runs(strategy_id=strategy_id, limit=60)
    prior = [
        r["scan_date"]
        for r in runs
        if r["universe_id"] == universe_id and r["scan_date"] < scan_date
    ]
    return max(prior) if prior else None


def breakout_actionable_tickers(report: dict, *, tiers: tuple[str, ...] = P.BREAKOUT_ACTIONABLE) -> list[dict]:
    rows = [_ticker_row(t) for t in report.get("tickers", []) if t.get("tier") in tiers]
    return sorted(rows, key=lambda x: (x.get("final_score") or 0), reverse=True)


def compute_persistence(
    repo: ScanRepository,
    *,
    as_of: date,
    universe_id: str = P.DAILY_BREAKOUT_UNIVERSE,
    lookback_days: int = P.PERSISTENCE_LOOKBACK_DAYS,
    min_days: int = P.PERSISTENCE_MIN_DAYS,
) -> list[dict[str, Any]]:
    start = as_of - timedelta(days=lookback_days + 3)
    runs = [
        r
        for r in repo.list_runs(strategy_id="breakout", limit=30)
        if r["universe_id"] == universe_id and start <= r["scan_date"] <= as_of
    ]
    counts: dict[str, int] = {}
    for run in runs:
        report = repo.load_report(
            strategy_id="breakout",
            universe_id=universe_id,
            scan_date=run["scan_date"],
        )
        if not report:
            continue
        for row in breakout_actionable_tickers(report):
            counts[row["ticker"]] = counts.get(row["ticker"], 0) + 1
    persistent = [
        {"ticker": ticker, "days_actionable": days}
        for ticker, days in counts.items()
        if days >= min_days
    ]
    return sorted(persistent, key=lambda x: (-x["days_actionable"], x["ticker"]))


def build_daily_payload(
    repo: ScanRepository,
    *,
    scan_date: date | None = None,
) -> dict[str, Any]:
    scan_date = scan_date or date.today()
    report = repo.load_report(
        strategy_id="breakout",
        universe_id=P.DAILY_BREAKOUT_UNIVERSE,
        scan_date=scan_date,
    )
    if not report:
        raise RuntimeError(f"No breakout scan for {P.DAILY_BREAKOUT_UNIVERSE} on {scan_date}")

    regime = report.get("market_regime") or {}
    regime_label = regime.get("label", "unknown")
    tier1 = breakout_actionable_tickers(report, tiers=(P.BREAKOUT_TIER1,))[: P.DAILY_TIER1_MAX]

    include_tier2 = regime_label != P.WEAK_REGIME_LABEL
    tier2: list[dict] = []
    if include_tier2:
        tier2 = [
            r
            for r in breakout_actionable_tickers(report, tiers=(P.BREAKOUT_TIER2,))
            if r["ticker"] not in {x["ticker"] for x in tier1}
        ][: P.DAILY_TIER2_MAX]

    prev_date = get_previous_scan_date(
        repo, scan_date=scan_date, strategy_id="breakout", universe_id=P.DAILY_BREAKOUT_UNIVERSE
    )
    new_entrants: list[str] = []
    dropped: list[str] = []
    if prev_date:
        prev_report = repo.load_report(
            strategy_id="breakout",
            universe_id=P.DAILY_BREAKOUT_UNIVERSE,
            scan_date=prev_date,
        )
        if prev_report:
            today_set = {r["ticker"] for r in tier1 + tier2}
            prev_set = {r["ticker"] for r in breakout_actionable_tickers(prev_report)}
            new_entrants = sorted(today_set - prev_set)
            dropped = sorted(prev_set - today_set)

    persistent = compute_persistence(repo, as_of=scan_date)[: P.WEEKLY_TABLE_MAX]

    return {
        "digest_type": "daily",
        "scan_date": str(scan_date),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "regime": regime,
        "summary": report.get("scan_summary") or {},
        "tier1": tier1,
        "tier2": tier2,
        "new_entrants": new_entrants,
        "dropped": dropped,
        "persistent": persistent,
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }


def build_weekly_payload(
    repo: ScanRepository,
    *,
    lynch_date: date | None = None,
) -> dict[str, Any]:
    lynch_date = lynch_date or date.today()
    swing_report = repo.get_latest_run(strategy_id="swing", universe_id=P.WEEKLY_SWING_UNIVERSE)
    if not swing_report:
        raise RuntimeError(f"No swing scan for {P.WEEKLY_SWING_UNIVERSE}")
    lynch_report = repo.load_report(
        strategy_id="lynch",
        universe_id=P.WEEKLY_LYNCH_UNIVERSE,
        scan_date=lynch_date,
    )
    if not lynch_report:
        latest = repo.get_latest_run(strategy_id="lynch", universe_id=P.WEEKLY_LYNCH_UNIVERSE)
        if latest and (lynch_date - latest["scan_date"]).days <= P.WEEKLY_LYNCH_MAX_AGE_DAYS:
            lynch_report = repo.load_report(
                strategy_id="lynch",
                universe_id=P.WEEKLY_LYNCH_UNIVERSE,
                scan_date=latest["scan_date"],
            )
    if not lynch_report:
        raise RuntimeError(f"No Lynch scan for {P.WEEKLY_LYNCH_UNIVERSE} near {lynch_date}")

    swing_full = repo.load_report(
        strategy_id="swing",
        universe_id=P.WEEKLY_SWING_UNIVERSE,
        scan_date=swing_report["scan_date"],
    )
    breakout_full = repo.get_latest_run(strategy_id="breakout", universe_id=P.DAILY_BREAKOUT_UNIVERSE)
    breakout_report = None
    if breakout_full:
        breakout_report = repo.load_report(
            strategy_id="breakout",
            universe_id=P.DAILY_BREAKOUT_UNIVERSE,
            scan_date=breakout_full["scan_date"],
        )

    etf_breakout = repo.get_latest_run(strategy_id="breakout", universe_id=P.WEEKLY_ETF_UNIVERSE)
    etf_swing = repo.get_latest_run(strategy_id="swing", universe_id=P.WEEKLY_ETF_UNIVERSE)

    b_triple = (
        {r["ticker"]: r for r in breakout_actionable_tickers(breakout_report, tiers=P.WEEKLY_TRIPLE_BREAKOUT_TIERS)}
        if breakout_report
        else {}
    )
    b_double = (
        {r["ticker"]: r for r in breakout_actionable_tickers(breakout_report, tiers=P.WEEKLY_DOUBLE_BREAKOUT_TIERS)}
        if breakout_report
        else {}
    )

    swing_setups = {}
    if swing_full:
        for t in swing_full.get("tickers", []):
            if t.get("tier") in ("SETUP_LONG", "SETUP_SHORT") and _is_swing_quality(t):
                swing_setups[t["ticker"]] = _swing_row(t)

    lynch_passed = {}
    for t in lynch_report.get("tickers", []):
        if t.get("passed") or t.get("eligible"):
            lynch_passed[t["ticker"]] = _lynch_row(t)

    triple = []
    for ticker in sorted(b_triple.keys()):
        if ticker in swing_setups and ticker in lynch_passed:
            triple.append(
                {
                    "ticker": ticker,
                    "breakout": b_triple[ticker],
                    "swing": swing_setups[ticker],
                    "lynch": lynch_passed[ticker],
                }
            )

    double_tech = []
    for ticker in sorted(b_double.keys()):
        if ticker in swing_setups and ticker not in {x["ticker"] for x in triple}:
            double_tech.append(
                {"ticker": ticker, "breakout": b_double[ticker], "swing": swing_setups[ticker]}
            )

    double_lynch = []
    for ticker in sorted(b_double.keys()):
        if ticker in lynch_passed and ticker not in {x["ticker"] for x in triple}:
            double_lynch.append(
                {"ticker": ticker, "breakout": b_double[ticker], "lynch": lynch_passed[ticker]}
            )

    swing_highlights = sorted(swing_setups.values(), key=lambda x: x.get("swing_score") or 0, reverse=True)[
        : P.WEEKLY_TABLE_MAX
    ]
    lynch_top = sorted(
        lynch_passed.values(),
        key=lambda x: (x.get("lynch_score") or 0),
        reverse=True,
    )[: P.WEEKLY_LYNCH_TOP_N]

    persistent = compute_persistence(repo, as_of=breakout_full["scan_date"] if breakout_full else lynch_date)[
        : P.WEEKLY_TABLE_MAX
    ]

    regime_week = []
    week_start = lynch_date - timedelta(days=7)
    for run in repo.list_runs(strategy_id="breakout", limit=15):
        if run["universe_id"] != P.DAILY_BREAKOUT_UNIVERSE:
            continue
        if run["scan_date"] < week_start:
            continue
        regime_week.append(
            {
                "scan_date": str(run["scan_date"]),
                "regime_label": run.get("regime_label"),
                "actionable_count": run.get("actionable_count"),
            }
        )
    regime_week.sort(key=lambda x: x["scan_date"])

    etf_highlights: list[dict] = []
    if etf_breakout and etf_swing and etf_breakout["scan_date"] == etf_swing["scan_date"]:
        eb = repo.load_report(
            strategy_id="breakout",
            universe_id=P.WEEKLY_ETF_UNIVERSE,
            scan_date=etf_breakout["scan_date"],
        )
        es = repo.load_report(
            strategy_id="swing",
            universe_id=P.WEEKLY_ETF_UNIVERSE,
            scan_date=etf_swing["scan_date"],
        )
        if eb and es:
            eb_map = {r["ticker"]: r for r in breakout_actionable_tickers(eb)}
            for t in es.get("tickers", []):
                if t.get("tier") in ("SETUP_LONG", "SETUP_SHORT"):
                    ticker = t["ticker"]
                    etf_highlights.append(
                        {
                            "ticker": ticker,
                            "breakout_tier": (eb_map.get(ticker) or {}).get("tier"),
                            "swing_tier": t.get("tier"),
                        }
                    )

    return {
        "digest_type": "weekly",
        "lynch_date": str(lynch_date),
        "swing_scan_date": str(swing_report["scan_date"]),
        "breakout_scan_date": str(breakout_full["scan_date"]) if breakout_full else None,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "triple_alignment": triple[: P.WEEKLY_TABLE_MAX],
        "double_tech": double_tech[: P.WEEKLY_TABLE_MAX],
        "double_lynch": double_lynch[: P.WEEKLY_TABLE_MAX],
        "swing_highlights": swing_highlights,
        "lynch_top": lynch_top,
        "persistent": persistent,
        "regime_week": regime_week,
        "etf_highlights": etf_highlights[: P.WEEKLY_TABLE_MAX],
        "lynch_summary": lynch_report.get("scan_summary") or {},
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }


def weekly_payload_path(for_date: date | None = None) -> Path:
    d = for_date or date.today()
    DIGEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return DIGEST_OUTPUT_DIR / f"weekly_{d.isoformat()}.json"


def save_weekly_payload(payload: dict, *, for_date: date | None = None) -> Path:
    path = weekly_payload_path(for_date)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_weekly_payload(for_date: date | None = None) -> dict | None:
    path = weekly_payload_path(for_date)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
