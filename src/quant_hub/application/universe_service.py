from __future__ import annotations

from pathlib import Path

from quant_hub.universes.registry import UniverseRegistry


class UniverseService:
    def __init__(self, registry: UniverseRegistry | None = None) -> None:
        self.registry = registry or UniverseRegistry()

    def list_universes(self) -> dict[str, str]:
        return self.registry.list_universes()

    def resolve(
        self,
        *,
        universe_id: str | None = None,
        tickers: list[str] | None = None,
        tickers_file: Path | str | None = None,
    ) -> tuple[str, list[str]]:
        return self.registry.resolve(
            universe_id=universe_id,
            tickers=tickers,
            tickers_file=tickers_file,
        )
