from __future__ import annotations

import json
import logging
from pathlib import Path

from quant_hub.config import PROJECT_ROOT, UNIVERSES_CONFIG
from quant_hub.data.tickers import load_tickers_file
from quant_hub.data.universe import fetch_universe

logger = logging.getLogger(__name__)


class UniverseRegistry:
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or UNIVERSES_CONFIG
        self._config = self._load_config()

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Universe config not found: {self.config_path}")
        return json.loads(self.config_path.read_text())

    def list_universes(self) -> dict[str, str]:
        return {
            uid: meta.get("name", uid)
            for uid, meta in self._config.get("universes", {}).items()
        }

    def resolve(
        self,
        universe_id: str | None = None,
        *,
        tickers: list[str] | None = None,
        tickers_file: Path | str | None = None,
    ) -> tuple[str, list[str]]:
        """
        Resolve universe tickers.

        Priority: explicit tickers > universe_id > tickers_file > error.
        Returns (universe_id, tickers).
        """
        if tickers:
            from quant_hub.data.tickers import _normalize_tickers

            normalized = _normalize_tickers(tickers)
            uid = universe_id or "custom"
            logger.info("Using %d tickers from CLI override (universe=%s)", len(normalized), uid)
            return uid, normalized

        if universe_id:
            return universe_id, self._resolve_id(universe_id)

        if tickers_file:
            path = Path(tickers_file)
            loaded = load_tickers_file(path)
            if not loaded:
                raise ValueError(f"Ticker file is empty: {path}")
            logger.info("Using %d tickers from %s", len(loaded), path)
            return "file", loaded

        raise ValueError("Specify --universe, --tickers, or --tickers-file")

    def get_eligibility_mode(self, universe_id: str) -> str:
        meta = self._config.get("universes", {}).get(universe_id, {})
        return meta.get("eligibility_mode", "stock")

    def is_lynch_enabled(self, universe_id: str) -> bool:
        meta = self._config.get("universes", {}).get(universe_id, {})
        return bool(meta.get("lynch_enabled", True))

    def get_refresh_config(self, universe_id: str) -> dict | None:
        meta = self._config.get("universes", {}).get(universe_id, {})
        refresh = meta.get("refresh")
        return refresh if isinstance(refresh, dict) else None

    def get_file_source_path(self, universe_id: str) -> Path | None:
        """Return resolved path for the first file-based source, if any."""
        meta = self._config.get("universes", {}).get(universe_id, {})
        for source in meta.get("sources", []):
            if source.get("type") != "file":
                continue
            rel = source.get("path", "")
            return PROJECT_ROOT / rel if not Path(rel).is_absolute() else Path(rel)
        return None

    def _resolve_id(self, universe_id: str) -> list[str]:
        universes = self._config.get("universes", {})
        if universe_id not in universes:
            known = ", ".join(sorted(universes))
            raise ValueError(f"Unknown universe '{universe_id}'. Known: {known}")

        meta = universes[universe_id]
        tickers: list[str] = []
        for source in meta.get("sources", []):
            tickers.extend(self._resolve_source(source))

        seen: set[str] = set()
        out: list[str] = []
        for t in tickers:
            if t not in seen:
                seen.add(t)
                out.append(t)

        if not out:
            raise ValueError(f"Universe '{universe_id}' resolved to zero tickers")
        logger.info("Resolved universe '%s' with %d tickers", universe_id, len(out))
        return out

    def _resolve_source(self, source: dict) -> list[str]:
        stype = source.get("type")
        if stype == "file":
            rel = source.get("path", "")
            path = PROJECT_ROOT / rel if not Path(rel).is_absolute() else Path(rel)
            loaded = load_tickers_file(path)
            if not loaded:
                raise ValueError(f"Universe file is empty: {path}")
            return loaded
        if stype == "screener":
            screener = source.get("screener", "most_actives")
            count = int(source.get("count", 250))
            if screener == "most_actives":
                return fetch_universe(size=count)
            raise ValueError(f"Unknown screener: {screener}")
        raise ValueError(f"Unknown universe source type: {stype}")
