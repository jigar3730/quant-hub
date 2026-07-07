"""Daily Command Center payload — cross-scanner, cross-universe 360 view.

Aggregates every scan run on a given date into a single briefing:
coverage (strategy x universe), multi-scanner convergence, and scan-to-scan
deltas (new / dropped / persistent actionable names). Metadata-first: it reads
lightweight run summaries and actionable ticker rows, not full ticker JSON, so
the landing page stays fast.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from quant_hub.dashboard.viz.labels import STRATEGY_DISPLAY
from quant_hub.infrastructure.postgres.repository import ScanRepository

# Strategies surfaced in the Command Center, in display order.
COMMAND_CENTER_STRATEGIES: tuple[str, ...] = ("breakout", "launchpad", "swing", "lynch")

# Number of trailing scans (per strategy+universe) used to judge persistence.
PERSISTENCE_MIN_APPEARANCES = 3
CONVERGENCE_MIN_STRATEGIES = 2


def _prior_run(
    repo: ScanRepository,
    *,
    strategy_id: str,
    universe_id: str,
    before: date,
) -> dict[str, Any] | None:
    """Most recent run for a strategy+universe strictly before `before`."""
    runs = repo.list_runs_filtered(
        strategy_id=strategy_id,
        universe_id=universe_id,
        until=before,
        limit=30,
    )
    for run in runs:
        if run["scan_date"] < before:
            return run
    return None


def _actionable_symbols(rows: list[dict[str, Any]]) -> set[str]:
    return {r["ticker"] for r in rows}


def build_command_center_payload(
    repo: ScanRepository,
    *,
    scan_date: date,
) -> dict[str, Any]:
    """Assemble the daily Command Center payload for `scan_date`."""
    runs = repo.list_runs_on_date(scan_date)

    coverage: list[dict[str, Any]] = []
    # ticker -> {strategy_id -> {tier, final_score, sector_etf, universe_id}}
    convergence_map: dict[str, dict[str, dict[str, Any]]] = {}
    deltas: list[dict[str, Any]] = []
    regime_label: str | None = None

    per_strategy: dict[str, dict[str, Any]] = {
        s: {"actionable": 0, "tier1": 0, "universes": 0} for s in COMMAND_CENTER_STRATEGIES
    }

    for run in runs:
        strategy_id = run["strategy_id"]
        universe_id = run["universe_id"]
        run_id = run["id"]
        actionable_rows = repo.list_actionable_tickers_for_run(run_id, strategy_id)

        if strategy_id == "breakout" and regime_label is None:
            regime_label = run.get("regime_label")

        coverage.append(
            {
                "strategy_id": strategy_id,
                "strategy_label": STRATEGY_DISPLAY.get(strategy_id, strategy_id.title()),
                "universe_id": universe_id,
                "run_id": run_id,
                "actionable_count": len(actionable_rows),
                "tier1_count": run.get("tier1_count", 0),
                "tier2_count": run.get("tier2_count", 0),
                "regime_label": run.get("regime_label"),
                "scan_time": run["scan_time"].isoformat() if run.get("scan_time") else None,
            }
        )

        if strategy_id in per_strategy:
            per_strategy[strategy_id]["actionable"] += len(actionable_rows)
            per_strategy[strategy_id]["tier1"] += run.get("tier1_count", 0) or 0
            per_strategy[strategy_id]["universes"] += 1

        for row in actionable_rows:
            ticker = row["ticker"]
            entry = convergence_map.setdefault(ticker, {})
            # Keep the strongest appearance per strategy (highest final_score).
            existing = entry.get(strategy_id)
            score = row.get("final_score")
            if existing is None or (score or 0) > (existing.get("final_score") or 0):
                entry[strategy_id] = {
                    "tier": row.get("tier"),
                    "final_score": score,
                    "sector_etf": row.get("sector_etf"),
                    "universe_id": universe_id,
                }

        prior = _prior_run(
            repo, strategy_id=strategy_id, universe_id=universe_id, before=scan_date
        )
        today_symbols = _actionable_symbols(actionable_rows)
        prior_symbols: set[str] = set()
        prior_date = None
        if prior:
            prior_date = prior["scan_date"]
            prior_symbols = _actionable_symbols(
                repo.list_actionable_tickers_for_run(prior["id"], strategy_id)
            )

        new_entrants = sorted(today_symbols - prior_symbols) if prior else []
        dropped = sorted(prior_symbols - today_symbols) if prior else []
        persistent = _persistent_symbols(
            repo,
            strategy_id=strategy_id,
            universe_id=universe_id,
            scan_date=scan_date,
            today_symbols=today_symbols,
        )
        deltas.append(
            {
                "strategy_id": strategy_id,
                "strategy_label": STRATEGY_DISPLAY.get(strategy_id, strategy_id.title()),
                "universe_id": universe_id,
                "prior_date": str(prior_date) if prior_date else None,
                "new_entrants": new_entrants,
                "dropped": dropped,
                "persistent": persistent,
            }
        )

    convergence = _build_convergence(convergence_map)

    return {
        "scan_date": str(scan_date),
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "regime_label": regime_label,
        "run_count": len(runs),
        "per_strategy": per_strategy,
        "coverage": coverage,
        "convergence": convergence,
        "convergence_count": len(convergence),
        "deltas": deltas,
    }


def _persistent_symbols(
    repo: ScanRepository,
    *,
    strategy_id: str,
    universe_id: str,
    scan_date: date,
    today_symbols: set[str],
    min_appearances: int = PERSISTENCE_MIN_APPEARANCES,
) -> list[dict[str, Any]]:
    """Tickers actionable on `scan_date` and in >= min_appearances recent runs."""
    if not today_symbols:
        return []
    runs = repo.list_runs_filtered(
        strategy_id=strategy_id,
        universe_id=universe_id,
        until=scan_date,
        limit=min_appearances + 3,
    )
    counts: dict[str, int] = dict.fromkeys(today_symbols, 0)
    for run in runs[: min_appearances + 2]:
        symbols = _actionable_symbols(
            repo.list_actionable_tickers_for_run(run["id"], strategy_id)
        )
        for ticker in today_symbols:
            if ticker in symbols:
                counts[ticker] += 1
    persistent = [
        {"ticker": ticker, "appearances": days}
        for ticker, days in counts.items()
        if days >= min_appearances
    ]
    return sorted(persistent, key=lambda x: (-x["appearances"], x["ticker"]))


def _build_convergence(
    convergence_map: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Tickers actionable in >= CONVERGENCE_MIN_STRATEGIES strategies."""
    rows: list[dict[str, Any]] = []
    for ticker, by_strategy in convergence_map.items():
        if len(by_strategy) < CONVERGENCE_MIN_STRATEGIES:
            continue
        sector = next(
            (v.get("sector_etf") for v in by_strategy.values() if v.get("sector_etf")),
            None,
        )
        best_score = max((v.get("final_score") or 0) for v in by_strategy.values())
        rows.append(
            {
                "ticker": ticker,
                "strategy_count": len(by_strategy),
                "strategies": sorted(by_strategy.keys()),
                "by_strategy": by_strategy,
                "sector_etf": sector,
                "best_score": best_score,
            }
        )
    return sorted(rows, key=lambda x: (-x["strategy_count"], -x["best_score"], x["ticker"]))
