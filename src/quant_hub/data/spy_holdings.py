"""Fetch S&P 500 constituents from State Street's published SPY holdings file."""

from __future__ import annotations

import io
import logging
import re
from urllib.error import URLError
from urllib.request import urlopen

import pandas as pd

from quant_hub.data.tickers import write_tickers_file

logger = logging.getLogger(__name__)

SPY_HOLDINGS_URL = (
    "https://www.ssga.com/us/en/intermediary/etfs/library-content/"
    "products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
)

MIN_EXPECTED_HOLDINGS = 450
MAX_EXPECTED_HOLDINGS = 520

_SKIP_TICKER_PREFIXES = ("CASH", "USD", "EUR", "GBP")
_CUSIP_LIKE = re.compile(r"^[0-9]+[A-Z]?$")


def vendor_to_yahoo(symbol: str) -> str:
    """Map vendor symbols (e.g. BRK.B) to Yahoo Finance tickers (BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def _should_skip_ticker(symbol: str) -> bool:
    upper = symbol.strip().upper()
    if not upper or upper == "-":
        return True
    if _CUSIP_LIKE.match(upper):
        return True
    return any(upper.startswith(prefix) for prefix in _SKIP_TICKER_PREFIXES)


def parse_spy_holdings_df(df: pd.DataFrame) -> list[str]:
    """Extract Yahoo-ready tickers from a parsed SSGA SPY holdings dataframe."""
    ticker_col = None
    for candidate in ("Ticker", "ticker", "Symbol", "symbol"):
        if candidate in df.columns:
            ticker_col = candidate
            break
    if ticker_col is None:
        raise ValueError(f"No ticker column in SPY holdings data; columns={list(df.columns)}")

    raw = df[ticker_col].dropna().astype(str).str.strip()
    symbols = [vendor_to_yahoo(s) for s in raw if s and not _should_skip_ticker(s)]
    tickers = load_tickers_file_from_symbols(symbols)
    if len(tickers) < MIN_EXPECTED_HOLDINGS:
        raise ValueError(
            f"SPY holdings parsed to {len(tickers)} tickers "
            f"(expected {MIN_EXPECTED_HOLDINGS}-{MAX_EXPECTED_HOLDINGS})"
        )
    return tickers


def load_tickers_file_from_symbols(symbols: list[str]) -> list[str]:
    """Normalize and dedupe symbols using the shared ticker validator."""
    from quant_hub.data.tickers import _normalize_tickers

    return _normalize_tickers(symbols)


def fetch_spy_holdings(*, url: str = SPY_HOLDINGS_URL) -> list[str]:
    """Download and parse the SSGA daily SPY holdings XLSX."""
    logger.info("Fetching SPY holdings from %s", url)
    try:
        with urlopen(url, timeout=60) as response:
            payload = response.read()
    except URLError as exc:
        raise RuntimeError(f"Failed to download SPY holdings: {exc}") from exc

    df = pd.read_excel(io.BytesIO(payload), skiprows=4, engine="openpyxl")
    tickers = parse_spy_holdings_df(df)
    logger.info("Parsed %d SPY holdings tickers", len(tickers))
    return tickers


def refresh_spy_holdings_file(
    output_path,
    *,
    url: str = SPY_HOLDINGS_URL,
) -> list[str]:
    """Fetch SPY holdings and write to a ticker list file."""
    tickers = fetch_spy_holdings(url=url)
    write_tickers_file(output_path, tickers)
    logger.info("Wrote %d tickers to %s", len(tickers), output_path)
    return tickers
