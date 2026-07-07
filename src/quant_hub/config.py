import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = DATA_DIR / "output"
HISTORY_DIR = DATA_DIR / "history"
UNIVERSES_CONFIG = DATA_DIR / "universes.json"
PRIMARY_INDEX_UNIVERSE = "sp500_index"
DEFAULT_TICKERS_FILE = DATA_DIR / "tickers.txt"
DRY_RUN_OUTPUT_DIR = OUTPUT_DIR / "dry_run"

UNIVERSE_SIZE = 250
MIN_TRADING_DAYS = 200
MIN_AVG_VOLUME = 750_000
MIN_PRICE = 10.0
ETF_MIN_TRADING_DAYS = 120
ETF_MIN_AVG_VOLUME = 500_000
ETF_MIN_PRICE = 5.0
MAX_REASONABLE_GROWTH = 3.0
PRICE_SPIKE_RATIO = 3.0
LOOKBACK_DAYS = 252
CACHE_TTL_HOURS = 24
CACHE_TTL_WEEKLY_HOURS = 168  # 7 days — swing runs weekly
CACHE_TTL_FUNDAMENTALS_HOURS = 168  # 7 days — quarterly fundamentals
PRICE_CACHE_SUBDIR = CACHE_DIR / "prices" / "1d" / "2y"
WEEKLY_CACHE_SUBDIR = CACHE_DIR / "prices" / "1wk" / "10y"
FUNDAMENTALS_CACHE_SUBDIR = CACHE_DIR / "fundamentals"

# ML foundation (Phase 1)
ML_DIR = DATA_DIR / "ml"
ML_FEATURES_DIR = ML_DIR / "features"
ML_MODELS_DIR = ML_DIR / "models"
FEATURE_SCHEMA_VERSION = "v3"
DEFAULT_LABEL_HORIZONS = (5, 10, 20, 63)
LABEL_RETURN_THRESHOLD_PCT = 2.0
BENCHMARK_TICKER_FOR_LABELS = "SPY"
# Extended daily cache for ML labels (backfill + forward returns)
ML_LABEL_LOOKBACK_DAYS = 1260  # ~5 calendar years
ML_LABEL_CACHE_SUBDIR = CACHE_DIR / "prices" / "1d" / "5y"
ML_LABEL_CACHE_TTL_HOURS = 8760  # 1 year — refresh via quant-ml warm-cache

SWING_PERIOD = "10y"
SWING_INTERVAL = "1wk"
SWING_MIN_BARS = 60
DEFAULT_SWING_OUTPUT_CSV = OUTPUT_DIR / "swing_setups.csv"

MEAN_REVERSION_LOOKBACK_DAYS = 600
MEAN_REVERSION_MIN_BARS = 520
MEAN_REVERSION_HIGH_CONVICTION = 71
MEAN_REVERSION_WATCHLIST = 62
DEFAULT_MEAN_REVERSION_UNIVERSE = "mean_reversion_core"

LYNCH_FETCH_WORKERS = 3
LYNCH_FETCH_BATCH_SIZE = 20
LYNCH_FETCH_BATCH_DELAY_SEC = 2.0
LYNCH_FETCH_RETRIES = 4
LYNCH_FETCH_RETRY_BASE_SEC = 1.0


def scan_output_paths(
    strategy_id: str,
    universe_id: str,
    *,
    dry_run: bool = False,
) -> dict[str, Path]:
    """Per-strategy/universe export paths under data/output/ (or dry_run/)."""
    root = DRY_RUN_OUTPUT_DIR if dry_run else OUTPUT_DIR
    base = root / strategy_id / universe_id
    names = {
        "breakout": ("scan_results.csv", "report.json", "summary.md"),
        "launchpad": ("scan_results.csv", "report.json", "summary.md"),
        "swing": ("setups.csv", "report.json", "summary.md"),
        "lynch": ("scan_results.csv", "report.json", "summary.md"),
        "mean_reversion": ("high_conviction.csv", "report.json", "summary.md"),
    }
    csv_name, json_name, md_name = names.get(
        strategy_id, ("scan_results.csv", "report.json", "summary.md")
    )
    paths = {
        "csv": base / csv_name,
        "json": base / json_name,
        "md": base / md_name,
    }
    if strategy_id == "mean_reversion":
        paths["watchlist_csv"] = base / "watchlist.csv"
        paths["full_scan_csv"] = base / "full_scan.csv"
    return paths

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

# Sector & commodity ETF universe (Option A scan list)
SECTOR_COMMODITY_ETFS = (
    "XLK",
    "XLC",
    "XLY",
    "XLP",
    "XLE",
    "XLF",
    "XLV",
    "XLI",
    "XLB",
    "XLU",
    "XLRE",
    "GLD",
    "SLV",
    "GDX",
    "PDBC",
    "CPER",
    "DBA",
)

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

# Breakout: sum of earnable factor points (7 technical factors; pattern/resistance cap at 5).
RAW_SCORE_MAX = 80
BREAKOUT_TIER2_NORMALIZED_MIN = 60.0
BREAKOUT_TIER1_NORMALIZED_MIN = 80.0
BREAKOUT_TIER1_FINAL_MIN = 70.0
BREAKOUT_TIER1_COMPRESSION_MIN = 8.0
BREAKOUT_TIER1_ACCUMULATION_MIN = 8.0
# Relative-volume factor points (5 pts ≈ ≥1.5× 20-day average volume).
BREAKOUT_TIER1_REL_VOLUME_MIN = 5.0
# Evaluate Bollinger squeeze as of prior bar(s) so breakout-day band expansion does not zero the score.
BREAKOUT_COMPRESSION_LAG_DAYS = 1
# Eligibility: long-term trend + 52-week position (relaxed for base breakouts / pullbacks).
BREAKOUT_MIN_PCT_ABOVE_52W_LOW = 0.30
BREAKOUT_MAX_PCT_BELOW_52W_HIGH = 0.40  # was 25% — allow deeper consolidations off highs
BREAKOUT_REQUIRE_SMA200_RISING = False

# Launchpad Reversal: 5-factor "coiled spring" engine (raw max 100).
# ma_tightness 25 + macd_zero_line 25 + atr_contraction 20 + volume_dry_up 15 + swing_low_vcp 15.
LAUNCHPAD_RAW_SCORE_MAX = 100
LAUNCHPAD_TIER1_NORMALIZED_MIN = 80.0
LAUNCHPAD_TIER2_NORMALIZED_MIN = 65.0
LAUNCHPAD_MIN_HISTORY_DAYS = 200
LAUNCHPAD_MIN_AVG_VOLUME = 750_000
LAUNCHPAD_MACD_ZERO_CROSS_LOOKBACK = 5
LAUNCHPAD_SWING_LOW_LOOKBACK = 40
LAUNCHPAD_SWING_HISTORY_DAYS = 120
# Min bars between distinct structural swing lows (collapse adjacent detections).
LAUNCHPAD_SWING_DEDUPE_MIN_GAP = 5

# ATR contraction (True Range shrinkage): Volatility_Ratio = ATR(short) / ATR(long).
LAUNCHPAD_ATR_SHORT_WINDOW = 14
LAUNCHPAD_ATR_LONG_WINDOW = 50
LAUNCHPAD_ATR_RATIO_STRONG = 0.70  # < 0.70 -> full points (ranges 30%+ tighter)
LAUNCHPAD_ATR_RATIO_OK = 0.80  # < 0.80 -> partial points (ranges 20%+ tighter)

# Volume dry-up (absolute supply exhaustion): mean(vol short) / SMA(vol long).
LAUNCHPAD_VOLUME_DRYUP_SHORT_WINDOW = 3
LAUNCHPAD_VOLUME_DRYUP_LONG_WINDOW = 50
LAUNCHPAD_VOLUME_DRYUP_STRONG = 0.50  # <= 0.50 -> full points (50%+ below baseline)
LAUNCHPAD_VOLUME_DRYUP_OK = 0.60  # <= 0.60 -> partial points (40%+ below baseline)

# VCP: latest structural pullback depth vs prior pullback depth (ratio).
LAUNCHPAD_VCP_RATIO_STRONG = 0.50  # <= 0.50 -> full points (textbook contraction)
LAUNCHPAD_VCP_RATIO_OK = 0.75  # <= 0.75 -> partial points


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql://quant:quant@localhost:5432/quant_hub",
    )
