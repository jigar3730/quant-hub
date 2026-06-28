"""Load static ticker lists from a config file."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from quant_hub.config import DEFAULT_TICKERS_FILE

logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _normalize_tickers(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in symbols:
        symbol = raw.strip().upper()
        if not symbol or symbol in seen:
            continue
        if not _TICKER_RE.match(symbol):
            logger.warning("Skipping invalid ticker symbol: %r", raw)
            continue
        seen.add(symbol)
        out.append(symbol)
    return out


def load_tickers_file(path: Path | str) -> list[str]:
    """Load tickers from a text or JSON config file."""
    path = Path(path)
    if not path.exists():
        return []

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return _normalize_tickers(data)
        if isinstance(data, dict):
            return _normalize_tickers(data.get("tickers", []))
        raise ValueError(f"Unsupported JSON structure in {path}")

    tickers: list[str] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "#" in stripped:
            stripped = stripped.split("#", 1)[0].strip()
        if "," in stripped:
            tickers.extend(part.strip() for part in stripped.split(","))
        else:
            tickers.append(stripped)
    return _normalize_tickers(tickers)


def resolve_universe(
    explicit: list[str] | None = None,
    *,
    tickers_file: Path | str | None = None,
    dynamic: bool = False,
) -> list[str]:
    """
    Resolve the scanner universe.

    Priority:
    1. Explicit tickers (CLI --tickers)
    2. Static config file (unless --dynamic-universe)
    3. Dynamic fetch (most-actives screener)
    """
    if explicit:
        tickers = _normalize_tickers(explicit)
        logger.info("Using %d tickers from CLI override", len(tickers))
        return tickers

    if not dynamic:
        path = Path(tickers_file) if tickers_file else DEFAULT_TICKERS_FILE
        if path.exists():
            tickers = load_tickers_file(path)
            if tickers:
                logger.info("Using %d tickers from %s", len(tickers), path)
                return tickers
            logger.warning("Ticker config %s is empty; falling back to dynamic universe", path)

    from quant_hub.data.universe import fetch_universe

    tickers = fetch_universe()
    logger.info("Using %d tickers from dynamic universe fetch", len(tickers))
    return tickers
