import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = DATA_DIR / "output"
HISTORY_DIR = DATA_DIR / "history"
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
CACHE_TTL_FUNDAMENTALS_HOURS = 168  # 7 days — quarterly fundamentals
PRICE_CACHE_SUBDIR = CACHE_DIR / "prices" / "1d" / "2y"
WEEKLY_CACHE_SUBDIR = CACHE_DIR / "prices" / "1wk" / "10y"
FUNDAMENTALS_CACHE_SUBDIR = CACHE_DIR / "fundamentals"

SWING_PERIOD = "10y"
SWING_INTERVAL = "1wk"
SWING_MIN_BARS = 60
DEFAULT_SWING_OUTPUT_CSV = OUTPUT_DIR / "swing_setups.csv"

DEFAULT_LYNCH_CSV = OUTPUT_DIR / "lynch_scan_results.csv"
DEFAULT_LYNCH_JSON = OUTPUT_DIR / "lynch_scan_report.json"
DEFAULT_LYNCH_MD = OUTPUT_DIR / "lynch_scan_summary.md"
LYNCH_FETCH_WORKERS = 8

LEGACY_BREAKOUT_OUTPUTS = {
    "csv": DEFAULT_OUTPUT_CSV,
    "json": DEFAULT_OUTPUT_JSON,
    "md": DEFAULT_OUTPUT_MD,
}


LEGACY_LYNCH_OUTPUTS = {
    "csv": DEFAULT_LYNCH_CSV,
    "json": DEFAULT_LYNCH_JSON,
    "md": DEFAULT_LYNCH_MD,
}


def scan_output_paths(strategy_id: str, universe_id: str) -> dict[str, Path]:
    """Per-strategy/universe export paths under data/output/."""
    base = OUTPUT_DIR / strategy_id / universe_id
    names = {
        "breakout": ("scan_results.csv", "report.json", "summary.md"),
        "swing": ("setups.csv", "report.json", "summary.md"),
        "lynch": ("scan_results.csv", "report.json", "summary.md"),
    }
    csv_name, json_name, md_name = names.get(
        strategy_id, ("scan_results.csv", "report.json", "summary.md")
    )
    return {
        "csv": base / csv_name,
        "json": base / json_name,
        "md": base / md_name,
    }

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
