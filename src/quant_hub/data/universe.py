import logging

import yfinance as yf

from quant_hub.config import FALLBACK_UNIVERSE, UNIVERSE_SIZE

logger = logging.getLogger(__name__)


def fetch_universe(size: int = UNIVERSE_SIZE) -> list[str]:
    """Fetch most-active US equities from yfinance screener."""
    try:
        result = yf.screen("most_actives", count=size)
        quotes = result.get("quotes", [])
        tickers = [q["symbol"] for q in quotes if q.get("symbol")]
        if tickers:
            return tickers[:size]
        logger.warning("yfinance most_actives screener returned no tickers")
    except Exception:
        logger.exception("yfinance screener unavailable; using fallback universe")

    return FALLBACK_UNIVERSE[:size]
