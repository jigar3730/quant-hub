from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from quant_hub.config import CACHE_TTL_FUNDAMENTALS_HOURS, FUNDAMENTALS_CACHE_SUBDIR
from quant_hub.data.fundamentals.types import FundamentalsSnapshot

logger = logging.getLogger(__name__)


class FundamentalsCache:
    def __init__(
        self,
        base_dir: Path | None = None,
        *,
        ttl_hours: float = CACHE_TTL_FUNDAMENTALS_HOURS,
    ) -> None:
        self.base_dir = base_dir or FUNDAMENTALS_CACHE_SUBDIR
        self.ttl = timedelta(hours=ttl_hours)

    def path_for(self, ticker: str) -> Path:
        return self.base_dir / f"{ticker.upper()}.json"

    def is_fresh(self, ticker: str) -> bool:
        path = self.path_for(ticker)
        if not path.exists():
            return False
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        return datetime.now() - mtime < self.ttl

    def read(self, ticker: str) -> FundamentalsSnapshot | None:
        path = self.path_for(ticker)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return FundamentalsSnapshot.from_dict(data)
        except Exception:
            logger.warning("Failed to read fundamentals cache for %s", ticker)
            return None

    def write(self, snapshot: FundamentalsSnapshot) -> None:
        path = self.path_for(snapshot.ticker)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot.to_dict(), indent=2))

    def partition(self, tickers: list[str], *, use_cache: bool) -> tuple[list[str], list[str]]:
        if not use_cache:
            return [], list(tickers)
        cached: list[str] = []
        stale: list[str] = []
        for ticker in tickers:
            if self.is_fresh(ticker):
                cached.append(ticker)
            else:
                stale.append(ticker)
        if cached:
            logger.info("Fundamentals cache hits: %d/%d tickers", len(cached), len(tickers))
        if stale:
            logger.info("Fundamentals cache misses: %d tickers to fetch", len(stale))
        return cached, stale
