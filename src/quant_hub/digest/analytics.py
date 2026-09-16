"""Build Launchpad and Lynch digest payloads from persisted scan runs."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from quant_hub.config import OUTPUT_DIR
from quant_hub.digest import policy as P
from quant_hub.digest.humanize import (
    format_peg,
    friendly_launchpad_tier,
    friendly_lynch_categories,
    launchpad_factor_highlights,
    launchpad_near_miss_why,
    launchpad_setup_text,
    launchpad_why,
    lynch_why,
)
from quant_hub.infrastructure.postgres.repository import ScanRepository

logger = logging.getLogger(__name__)

DIGEST_OUTPUT_DIR = OUTPUT_DIR / "digest"


def _launchpad_row(ticker: dict[str, Any]) -> dict[str, Any]:
    summary = ticker.get("summary") or {}
    normalized = summary.get("normalized_score", ticker.get("normalized_score"))
    final_score = summary.get(
        "final_adjusted_score",
        ticker.get("final_score", normalized),
    )
    trend_raw = ((ticker.get("scores") or {}).get("trend_proximity_match") or {}).get("raw") or {}
    return {
        "ticker": ticker["ticker"],
        "tier": ticker.get("tier"),
        "tier_label": friendly_launchpad_tier(ticker.get("tier")),
        "final_score": final_score,
        "normalized_score": normalized,
        "sector_etf": ticker.get("sector_etf"),
        "tier_reason": ticker.get("tier_reason"),
        "price": trend_raw.get("price"),
        "why": launchpad_why(ticker),
        "factor_highlights": launchpad_factor_highlights(ticker),
        "setup": launchpad_setup_text(ticker),
    }


def _launchpad_near_miss_row(ticker: dict[str, Any]) -> dict[str, Any]:
    row = _launchpad_row(ticker)
    row["why"] = launchpad_near_miss_why(ticker)
    return row


def _lynch_row(ticker: dict[str, Any]) -> dict[str, Any]:
    categories = ticker.get("categories") or []
    return {
        "ticker": ticker["ticker"],
        "lynch_score": ticker.get("lynch_score"),
        "categories": categories,
        "category_label": friendly_lynch_categories(categories),
        "pe_ratio": ticker.get("pe_ratio"),
        "peg_ratio": ticker.get("peg_ratio"),
        "peg_label": format_peg(ticker.get("peg_ratio")),
        "company_name": ticker.get("company_name"),
        "tier_reason": ticker.get("tier_reason"),
        "why": lynch_why(ticker),
    }


def launchpad_actionable_tickers(tickers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize and rank actionable Launchpad rows."""
    rows = [_launchpad_row(t) for t in tickers if t.get("tier") in P.LAUNCHPAD_ACTIONABLE]
    return sorted(
        rows,
        key=lambda row: (row.get("final_score") or 0, row.get("ticker") or ""),
        reverse=True,
    )


def _near_miss_tickers(tickers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Top Tier 3 (below-threshold) rows, for when a universe has no actionable hits."""
    rows = [_launchpad_near_miss_row(t) for t in tickers if t.get("tier") == "Tier 3"]
    rows.sort(key=lambda row: (row.get("normalized_score") or 0, row.get("ticker") or ""), reverse=True)
    return rows[: P.DAILY_NEAR_MISS_MAX]


def _prior_run(
    repo: ScanRepository,
    *,
    scan_date: date,
    strategy_id: str,
    universe_id: str,
) -> dict[str, Any] | None:
    runs = repo.list_runs_filtered(
        strategy_id=strategy_id,
        universe_id=universe_id,
        until=scan_date,
        limit=30,
    )
    return next((run for run in runs if run["scan_date"] < scan_date), None)


def _persistent_launchpad(
    repo: ScanRepository,
    *,
    scan_date: date,
    universe_id: str,
    current_tickers: set[str],
) -> list[dict[str, Any]]:
    if not current_tickers:
        return []
    earliest = scan_date - timedelta(days=P.PERSISTENCE_LOOKBACK_DAYS + 3)
    runs = [
        run
        for run in repo.list_runs(
            strategy_id=P.LAUNCHPAD_STRATEGY,
            limit=30,
        )
        if (
            run["universe_id"] == universe_id
            and earliest <= run["scan_date"] <= scan_date
        )
    ]
    appearances = dict.fromkeys(current_tickers, 0)
    for run in runs:
        details = repo.list_ticker_details_for_run(run["id"])
        symbols = {t["ticker"] for t in details if t.get("tier") in P.LAUNCHPAD_ACTIONABLE}
        for ticker in current_tickers & symbols:
            appearances[ticker] += 1
    persistent = [
        {"ticker": ticker, "days_actionable": days}
        for ticker, days in appearances.items()
        if days >= P.PERSISTENCE_MIN_DAYS
    ]
    return sorted(persistent, key=lambda row: (-row["days_actionable"], row["ticker"]))


def _build_universe_block(
    repo: ScanRepository,
    *,
    scan_date: date,
    universe_id: str,
    run: dict[str, Any],
    report: dict[str, Any] | None,
    regime_label: str,
) -> dict[str, Any]:
    details = repo.list_ticker_details_for_run(run["id"])
    actionable = launchpad_actionable_tickers(details)
    tier1 = [row for row in actionable if row["tier"] == P.LAUNCHPAD_TIER1][: P.DAILY_TIER1_MAX]
    tier2 = []
    if regime_label != P.WEAK_REGIME_LABEL:
        tier2 = [row for row in actionable if row["tier"] == P.LAUNCHPAD_TIER2][: P.DAILY_TIER2_MAX]

    near_misses: list[dict[str, Any]] = []
    if not tier1 and not tier2:
        near_misses = _near_miss_tickers(details)

    # Deltas describe the scanner's actionable set, not just the names shown
    # after digest caps or weak-regime Tier 2 suppression.
    current_tickers = {row["ticker"] for row in actionable}
    prior = _prior_run(
        repo,
        scan_date=scan_date,
        strategy_id=P.LAUNCHPAD_STRATEGY,
        universe_id=universe_id,
    )
    prior_tickers: set[str] = set()
    if prior:
        prior_tickers = {
            row["ticker"]
            for row in launchpad_actionable_tickers(repo.list_ticker_details_for_run(prior["id"]))
        }

    return {
        "universe_id": universe_id,
        "universe_label": P.UNIVERSE_LABELS.get(universe_id, universe_id),
        "scan_date": str(run["scan_date"]),
        "summary": (report or {}).get("scan_summary") or {},
        "tier1": tier1,
        "tier2": tier2,
        "near_misses": near_misses,
        "new_entrants": sorted(current_tickers - prior_tickers) if prior else [],
        "dropped": sorted(prior_tickers - current_tickers) if prior else [],
        "persistent": _persistent_launchpad(
            repo,
            scan_date=scan_date,
            universe_id=universe_id,
            current_tickers=current_tickers,
        ),
    }


def build_daily_payload(
    repo: ScanRepository,
    *,
    scan_date: date | None = None,
) -> dict[str, Any]:
    """Build the daily premarket Launchpad brief across all scanned universes."""
    scan_date = scan_date or date.today()

    primary_run = repo.get_latest_run(
        strategy_id=P.LAUNCHPAD_STRATEGY,
        universe_id=P.DAILY_LAUNCHPAD_UNIVERSE,
        scan_date=scan_date,
    )
    if not primary_run:
        raise RuntimeError(f"No Launchpad scan for {P.DAILY_LAUNCHPAD_UNIVERSE} on {scan_date}")

    primary_report = repo.load_report(
        strategy_id=P.LAUNCHPAD_STRATEGY,
        universe_id=P.DAILY_LAUNCHPAD_UNIVERSE,
        scan_date=scan_date,
    )
    regime = (primary_report or {}).get("market_regime") or {}
    regime_label = regime.get("label", primary_run.get("regime_label", "unknown"))

    universes: list[dict[str, Any]] = []
    for universe_id in P.DAILY_UNIVERSES:
        if universe_id == P.DAILY_LAUNCHPAD_UNIVERSE:
            run, report = primary_run, primary_report
        else:
            run = repo.get_latest_run(
                strategy_id=P.LAUNCHPAD_STRATEGY,
                universe_id=universe_id,
                scan_date=scan_date,
            )
            if not run:
                logger.warning(
                    "No Launchpad scan for %s on %s — skipping from daily digest",
                    universe_id,
                    scan_date,
                )
                continue
            report = repo.load_report(
                strategy_id=P.LAUNCHPAD_STRATEGY,
                universe_id=universe_id,
                scan_date=scan_date,
            )
        universes.append(
            _build_universe_block(
                repo,
                scan_date=scan_date,
                universe_id=universe_id,
                run=run,
                report=report,
                regime_label=regime_label,
            )
        )

    totals = {
        "tier1": sum(len(u["tier1"]) for u in universes),
        "tier2": sum(len(u["tier2"]) for u in universes),
        "near_misses": sum(len(u["near_misses"]) for u in universes),
    }
    totals["actionable"] = totals["tier1"] + totals["tier2"]

    return {
        "digest_type": "daily",
        "scan_date": str(scan_date),
        "launchpad_scan_date": str(primary_run["scan_date"]),
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "regime": regime,
        "universes": universes,
        "totals": totals,
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }


def _latest_recent_launchpad_run(repo: ScanRepository, *, lynch_date: date) -> dict[str, Any] | None:
    run = repo.get_latest_run(
        strategy_id=P.LAUNCHPAD_STRATEGY,
        universe_id=P.WEEKLY_LAUNCHPAD_UNIVERSE,
    )
    if not run or run["scan_date"] > lynch_date:
        return None
    if (lynch_date - run["scan_date"]).days > P.WEEKLY_LAUNCHPAD_MAX_AGE_DAYS:
        return None
    return run


def build_weekly_payload(
    repo: ScanRepository,
    *,
    lynch_date: date | None = None,
) -> dict[str, Any]:
    """Build the weekly Lynch ranking and optional Launchpad overlap."""
    lynch_date = lynch_date or date.today()
    lynch_run = repo.get_latest_run(
        strategy_id=P.LYNCH_STRATEGY,
        universe_id=P.WEEKLY_LYNCH_UNIVERSE,
        scan_date=lynch_date,
    )
    if not lynch_run:
        raise RuntimeError(f"No Lynch scan for {P.WEEKLY_LYNCH_UNIVERSE} on {lynch_date}")

    lynch_rows = [
        _lynch_row(ticker)
        for ticker in repo.list_ticker_details_for_run(lynch_run["id"])
        if ticker.get("passed") or ticker.get("eligible")
    ]
    lynch_top = sorted(
        lynch_rows,
        key=lambda row: (row.get("lynch_score") or 0, row["ticker"]),
        reverse=True,
    )[: P.WEEKLY_LYNCH_TOP_N]

    launchpad_run = _latest_recent_launchpad_run(repo, lynch_date=lynch_date)
    launchpad_overlap: list[dict[str, Any]] = []
    if launchpad_run:
        launchpad_by_ticker = {
            row["ticker"]: row
            for row in launchpad_actionable_tickers(
                repo.list_ticker_details_for_run(launchpad_run["id"])
            )
        }
        launchpad_overlap = [
            {
                "ticker": lynch["ticker"],
                "lynch": lynch,
                "launchpad": launchpad_by_ticker[lynch["ticker"]],
            }
            for lynch in lynch_top
            if lynch["ticker"] in launchpad_by_ticker
        ]

    return {
        "digest_type": "weekly",
        "lynch_date": str(lynch_run["scan_date"]),
        "launchpad_scan_date": str(launchpad_run["scan_date"]) if launchpad_run else None,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "lynch_top": lynch_top,
        "launchpad_overlap": launchpad_overlap,
        "lynch_summary": (repo.load_report(
            strategy_id=P.LYNCH_STRATEGY,
            universe_id=P.WEEKLY_LYNCH_UNIVERSE,
            scan_date=lynch_run["scan_date"],
        ) or {}).get("scan_summary") or {},
        "policy_footer": P.DIGEST_POLICY_FOOTER,
    }


def weekly_payload_path(for_date: date | None = None) -> Path:
    digest_date = for_date or date.today()
    DIGEST_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return DIGEST_OUTPUT_DIR / f"weekly_{digest_date.isoformat()}.json"


def save_weekly_payload(payload: dict[str, Any], *, for_date: date | None = None) -> Path:
    path = weekly_payload_path(for_date)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_weekly_payload(for_date: date | None = None) -> dict[str, Any] | None:
    path = weekly_payload_path(for_date)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
