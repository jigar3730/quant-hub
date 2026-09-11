"""Command Center payload for the Launchpad and Lynch research workflow."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from quant_hub.dashboard.viz.labels import STRATEGY_DISPLAY
from quant_hub.infrastructure.postgres.repository import ScanRepository

COMMAND_CENTER_STRATEGIES: tuple[str, ...] = ("launchpad", "lynch")
PERSISTENCE_MIN_APPEARANCES = 3


def _prior_run(
    repo: ScanRepository,
    *,
    strategy_id: str,
    universe_id: str,
    before: date,
) -> dict[str, Any] | None:
    return repo.get_prior_run(strategy_id=strategy_id, universe_id=universe_id, before=before)


def _symbols(rows: list[dict[str, Any]]) -> set[str]:
    return {row["ticker"] for row in rows}


def _persistent_symbols(
    repo: ScanRepository,
    *,
    strategy_id: str,
    universe_id: str,
    scan_date: date,
    current: set[str],
) -> list[dict[str, Any]]:
    if not current:
        return []
    run_ids = repo.list_run_ids_filtered(
        strategy_id=strategy_id,
        universe_id=universe_id,
        until=scan_date,
        limit=PERSISTENCE_MIN_APPEARANCES + 3,
    )[: PERSISTENCE_MIN_APPEARANCES + 2]
    counts = repo.count_actionable_appearances(run_ids, current, strategy_id)
    return sorted(
        (
            {"ticker": ticker, "appearances": counts.get(ticker, 0)}
            for ticker in current
            if counts.get(ticker, 0) >= PERSISTENCE_MIN_APPEARANCES
        ),
        key=lambda row: (-row["appearances"], row["ticker"]),
    )


def build_command_center_payload(
    repo: ScanRepository,
    *,
    scan_date: date,
) -> dict[str, Any]:
    """Assemble Launchpad/Lynch coverage, overlap, and scan deltas."""
    runs = [
        run
        for run in repo.list_runs_on_date(scan_date)
        if run["strategy_id"] in COMMAND_CENTER_STRATEGIES
    ]
    coverage: list[dict[str, Any]] = []
    deltas: list[dict[str, Any]] = []
    actionable_tickers: list[dict[str, Any]] = []
    by_ticker: dict[str, dict[str, dict[str, Any]]] = {}
    per_strategy = {
        strategy: {"actionable": 0, "tier1": 0, "universes": 0}
        for strategy in COMMAND_CENTER_STRATEGIES
    }
    regime_label: str | None = None

    for run in runs:
        strategy_id = run["strategy_id"]
        universe_id = run["universe_id"]
        rows = repo.list_actionable_tickers_for_run(run["id"], strategy_id)
        if strategy_id == "launchpad" and regime_label is None:
            regime_label = run.get("regime_label")
        coverage.append(
            {
                "strategy_id": strategy_id,
                "strategy_label": STRATEGY_DISPLAY[strategy_id],
                "universe_id": universe_id,
                "run_id": run["id"],
                "actionable_count": len(rows),
                "tier1_count": run.get("tier1_count", 0),
                "tier2_count": run.get("tier2_count", 0),
                "regime_label": run.get("regime_label"),
                "scan_time": run["scan_time"].isoformat() if run.get("scan_time") else None,
            }
        )
        per_strategy[strategy_id]["actionable"] += len(rows)
        per_strategy[strategy_id]["tier1"] += run.get("tier1_count", 0) or 0
        per_strategy[strategy_id]["universes"] += 1

        for row in rows:
            by_ticker.setdefault(row["ticker"], {})[strategy_id] = {
                "tier": row.get("tier"),
                "final_score": row.get("final_score"),
                "universe_id": universe_id,
            }
            actionable_tickers.append(
                {
                    **row,
                    "universe_id": universe_id,
                    "run_id": run["id"],
                    "regime_label": run.get("regime_label"),
                    "scan_time": run["scan_time"].isoformat() if run.get("scan_time") else None,
                }
            )

        prior = _prior_run(
            repo,
            strategy_id=strategy_id,
            universe_id=universe_id,
            before=scan_date,
        )
        current = _symbols(rows)
        prior_symbols = (
            _symbols(repo.list_actionable_tickers_for_run(prior["id"], strategy_id))
            if prior
            else set()
        )
        deltas.append(
            {
                "strategy_id": strategy_id,
                "strategy_label": STRATEGY_DISPLAY[strategy_id],
                "universe_id": universe_id,
                "prior_date": str(prior["scan_date"]) if prior else None,
                "new_entrants": sorted(current - prior_symbols) if prior else [],
                "dropped": sorted(prior_symbols - current) if prior else [],
                "persistent": _persistent_symbols(
                    repo,
                    strategy_id=strategy_id,
                    universe_id=universe_id,
                    scan_date=scan_date,
                    current=current,
                ),
            }
        )

    actionable_tickers.sort(key=lambda row: (-(row.get("final_score") or 0), row["ticker"]))

    overlap = [
        {
            "ticker": ticker,
            "launchpad": appearances["launchpad"],
            "lynch": appearances["lynch"],
        }
        for ticker, appearances in by_ticker.items()
        if {"launchpad", "lynch"} <= appearances.keys()
    ]
    overlap.sort(
        key=lambda row: (
            -(row["launchpad"].get("final_score") or 0),
            -(row["lynch"].get("final_score") or 0),
            row["ticker"],
        )
    )
    return {
        "scan_date": str(scan_date),
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "regime_label": regime_label,
        "run_count": len(runs),
        "per_strategy": per_strategy,
        "coverage": coverage,
        "actionable_tickers": actionable_tickers,
        "launchpad_lynch_overlap": overlap,
        "overlap_count": len(overlap),
        "deltas": deltas,
    }
