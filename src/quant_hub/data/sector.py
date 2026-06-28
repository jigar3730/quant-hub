import logging

import yfinance as yf

from quant_hub.config import (
    FALLBACK_SECTOR_ETF,
    INDUSTRY_TO_ETF,
    SECTOR_TO_ETF,
)

logger = logging.getLogger(__name__)


def resolve_sector_etf(ticker: str, info: dict | None = None) -> str:
    """Map ticker to sector ETF using yfinance metadata."""
    if info is None:
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception:
            logger.warning("Could not fetch info for %s; using fallback ETF", ticker)
            return FALLBACK_SECTOR_ETF

    industry = info.get("industry") or ""
    sector = info.get("sector") or ""

    if industry in INDUSTRY_TO_ETF:
        return INDUSTRY_TO_ETF[industry]
    if sector in SECTOR_TO_ETF:
        return SECTOR_TO_ETF[sector]

    logger.warning(
        "Unmapped sector for %s (sector=%s, industry=%s); using %s",
        ticker,
        sector,
        industry,
        FALLBACK_SECTOR_ETF,
    )
    return FALLBACK_SECTOR_ETF
