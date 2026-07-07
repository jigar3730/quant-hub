"""Helpers for batch scans across configured universes."""

from __future__ import annotations

from quant_hub.config import UNIVERSES_CONFIG
from quant_hub.universes.registry import UniverseRegistry


def list_universe_ids(
    registry: UniverseRegistry | None = None,
    *,
    strategy: str | None = None,
    explicit: list[str] | None = None,
) -> list[str]:
    """
    Return sorted universe ids for batch jobs.

    strategy:
      - None / \"breakout\" / \"swing\" — all configured universes
      - \"lynch\" — universes with lynch_enabled (default true; false skips ETF list)
      - \"launchpad\" — stock-mode universes only (rubric is single-stock; ETF-mode skipped)
    """
    reg = registry or UniverseRegistry()
    if explicit:
        known = set(reg.list_universes())
        unknown = [uid for uid in explicit if uid not in known]
        if unknown:
            raise ValueError(f"Unknown universe(s): {', '.join(sorted(unknown))}")
        ids = list(explicit)
    else:
        ids = sorted(reg.list_universes())

    if strategy == "lynch":
        ids = [uid for uid in ids if reg.is_lynch_enabled(uid)]
    elif strategy == "launchpad":
        ids = [uid for uid in ids if reg.get_eligibility_mode(uid) != "etf"]
    return ids


def default_registry() -> UniverseRegistry:
    return UniverseRegistry(config_path=UNIVERSES_CONFIG)
