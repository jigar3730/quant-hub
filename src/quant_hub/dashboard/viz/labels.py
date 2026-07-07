"""Analyst-friendly display labels for the dashboard."""

from __future__ import annotations

from datetime import date

STRATEGY_DISPLAY = {
    "command_center": "Command Center",
    "breakout": "Breakout",
    "launchpad": "Launchpad Reversal",
    "swing": "Swing",
    "lynch": "Lynch",
    "mean_reversion": "Mean Reversion",
}

TIER_FRIENDLY = {
    "Tier 1": "High conviction",
    "Tier 2": "Watchlist",
    "Tier 3": "Monitor",
    "filtered": "Excluded",
    "SETUP_LONG": "Long setup",
    "SETUP_SHORT": "Short setup",
    "HIGH_CONVICTION": "High conviction",
    "WATCHLIST": "Watchlist",
    "fast_grower": "Fast grower",
    "stalwart": "Stalwart",
    "asset_play": "Asset play",
    "passed": "Passed",
}

TIER_FRIENDLY_SHORT = {
    "Tier 1": "High conv.",
    "Tier 2": "Watchlist",
    "Tier 3": "Monitor",
    "filtered": "Excluded",
}


def format_report_label(
    *,
    strategy_id: str,
    universe_id: str,
    scan_date: date | str | None,
) -> str:
    """Human-readable report line for headers and captions."""
    strategy = STRATEGY_DISPLAY.get(strategy_id, strategy_id.replace("_", " ").title())
    date_s = str(scan_date) if scan_date else "latest"
    universe = universe_id.replace("_", " ").upper()
    return f"{universe} · {strategy} · {date_s}"


def tier_friendly(tier: str, *, short: bool = False) -> str:
    mapping = TIER_FRIENDLY_SHORT if short else TIER_FRIENDLY
    return mapping.get(tier, tier.replace("_", " ").title())


def format_universe_option(universe_id: str, description: str, *, has_scan: bool) -> str:
    badge = "scanned" if has_scan else "no scan"
    return f"{universe_id} — {description} ({badge})"
