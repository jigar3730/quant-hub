"""Refresh file-based universes from external holdings sources."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from quant_hub.data.spy_holdings import SPY_HOLDINGS_URL, refresh_spy_holdings_file
from quant_hub.universes.registry import UniverseRegistry

logger = logging.getLogger(__name__)

REFRESH_PROVIDERS = {
    "ssga_spy": refresh_spy_holdings_file,
}


@dataclass(frozen=True)
class RefreshResult:
    universe_id: str
    provider: str
    output_path: Path
    ticker_count: int
    refreshed_at: str
    source_url: str | None = None


class UniverseRefreshService:
    def __init__(self, registry: UniverseRegistry | None = None) -> None:
        self.registry = registry or UniverseRegistry()

    def refresh(self, universe_id: str, *, dry_run: bool = False) -> RefreshResult:
        universes = self.registry.list_universes()
        if universe_id not in universes:
            known = ", ".join(sorted(universes))
            raise ValueError(f"Unknown universe '{universe_id}'. Known: {known}")

        refresh_cfg = self.registry.get_refresh_config(universe_id)
        if not refresh_cfg:
            raise ValueError(
                f"Universe '{universe_id}' has no refresh provider configured in universes.json"
            )

        provider = refresh_cfg.get("provider")
        if provider not in REFRESH_PROVIDERS:
            raise ValueError(
                f"Unknown refresh provider '{provider}' for universe '{universe_id}'. "
                f"Known: {', '.join(sorted(REFRESH_PROVIDERS))}"
            )

        output_path = self.registry.get_file_source_path(universe_id)
        if output_path is None:
            raise ValueError(f"Universe '{universe_id}' has no file source to refresh")

        source_url = refresh_cfg.get("url") or (
            SPY_HOLDINGS_URL if provider == "ssga_spy" else None
        )
        refreshed_at = datetime.now(UTC).replace(microsecond=0).isoformat()

        if dry_run:
            logger.info(
                "Dry run: would refresh %s via %s -> %s",
                universe_id,
                provider,
                output_path,
            )
            return RefreshResult(
                universe_id=universe_id,
                provider=provider,
                output_path=output_path,
                ticker_count=0,
                refreshed_at=refreshed_at,
                source_url=source_url,
            )

        refresh_fn = REFRESH_PROVIDERS[provider]
        if provider == "ssga_spy":
            tickers = refresh_fn(output_path, url=source_url or SPY_HOLDINGS_URL)
        else:
            tickers = refresh_fn(output_path)

        meta_path = output_path.parent / f"{output_path.stem}.meta.json"
        meta_path.write_text(
            json.dumps(
                {
                    "universe_id": universe_id,
                    "provider": provider,
                    "source_url": source_url,
                    "ticker_count": len(tickers),
                    "refreshed_at": refreshed_at,
                },
                indent=2,
            )
            + "\n"
        )

        logger.info(
            "Refreshed universe '%s': %d tickers written to %s",
            universe_id,
            len(tickers),
            output_path,
        )
        return RefreshResult(
            universe_id=universe_id,
            provider=provider,
            output_path=output_path,
            ticker_count=len(tickers),
            refreshed_at=refreshed_at,
            source_url=source_url,
        )
