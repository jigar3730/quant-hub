import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = DATA_DIR / "output"
UNIVERSES_CONFIG = DATA_DIR / "universes.json"
DEFAULT_TICKERS_FILE = DATA_DIR / "tickers.txt"
DEFAULT_OUTPUT_CSV = OUTPUT_DIR / "breakout_scan_results.csv"
DEFAULT_OUTPUT_JSON = OUTPUT_DIR / "breakout_scan_report.json"
DEFAULT_OUTPUT_MD = OUTPUT_DIR / "breakout_scan_summary.md"
DRY_RUN_OUTPUT_DIR = OUTPUT_DIR / "dry_run"

UNIVERSE_SIZE = 250
MIN_TRADING_DAYS = 200
MIN_AVG_VOLUME = 750_000
MIN_PRICE = 10.0
MAX_REASONABLE_GROWTH = 3.0
PRICE_SPIKE_RATIO = 3.0
LOOKBACK_DAYS = 252
CACHE_TTL_HOURS = 24
CACHE_TTL_WEEKLY_HOURS = 168  # 7 days — swing runs weekly
PRICE_CACHE_SUBDIR = CACHE_DIR / "prices" / "1d" / "2y"
WEEKLY_CACHE_SUBDIR = CACHE_DIR / "prices" / "1wk" / "10y"

SWING_PERIOD = "10y"
SWING_INTERVAL = "1wk"
SWING_MIN_BARS = 60
DEFAULT_SWING_OUTPUT_CSV = OUTPUT_DIR / "swing_setups.csv"

BENCHMARK_TICKER = "SPY"
FALLBACK_SECTOR_ETF = "SPY"

INDUSTRY_TO_ETF: dict[str, str] = {
    "Semiconductors": "SOXX",
    "Software - Infrastructure": "IGV",
    "Software - Application": "IGV",
    "Software": "IGV",
    "Internet Content & Information": "IGV",
    "Biotechnology": "XBI",
    "Banks - Regional": "KRE",
    "Banks - Diversified": "XLF",
    "Oil & Gas E&P": "XLE",
    "Oil & Gas Integrated": "XLE",
    "Aerospace & Defense": "ITA",
    "Utilities - Regulated Electric": "XLU",
    "REIT - Residential": "VNQ",
    "REIT - Industrial": "VNQ",
}

SECTOR_TO_ETF: dict[str, str] = {
    "Technology": "XLK",
    "Communication Services": "XLC",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Real Estate": "VNQ",
    "Utilities": "XLU",
}

ALL_SECTOR_ETFS = sorted(set(SECTOR_TO_ETF.values()) | set(INDUSTRY_TO_ETF.values()))

FALLBACK_UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AMD",
    "AVGO",
    "NFLX",
]

RAW_SCORE_MAX = 120


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://quant:quant@localhost:5432/quant_hub",
    )
