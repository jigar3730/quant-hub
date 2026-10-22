"""Sector-ETF swing scanner tunables.

Constants are UPPER_CASE like ``config.py`` / ``lynch/config.py``; ``SwingParams`` bundles the
rule thresholds so tests can override them without monkeypatching module globals.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass

from quant_hub.config import ETF_MIN_PRICE

STRATEGY_ID = "sector_etf_swing"
UNIVERSE_ID = "sector_etfs"
JOB_NAME = "sector-swing-daily"
POSITIONS_JOB_NAME = "sector-swing-positions"
SCHEMA_VERSION = 1

# Tier keys must match ScanRepository._tier_counts_from_report for non-Lynch strategies.
TIER_TRIGGER = "Tier 1"
TIER_WATCH = "Tier 2"
TIER_EXTENDED = "Tier 3"
TIER_FILTERED = "filtered"
TIERS = (TIER_TRIGGER, TIER_WATCH, TIER_EXTENDED, TIER_FILTERED)

# Filter reason vocabulary (eligibility.fail_reason / ticker_results.filter_reason).
REASON_NO_PRICE_DATA = "no_price_data"
REASON_INSUFFICIENT_HISTORY = "insufficient_history"
REASON_DATA_QUALITY = "data_quality"
REASON_ILLIQUID = "illiquid"
REASON_NOT_LEADER = "not_leader"
REASON_TREND_FAIL = "trend_fail"
REASON_STOP_TOO_WIDE = "stop_too_wide"
REASON_CORRELATED = "correlated"
REASON_SIZE_ZERO = "size_zero"
REASON_SIGNAL_CAP = "signal_cap"  # a qualified setup beyond MAX_NEW_SIGNALS (not in spec v2)
REASON_ALREADY_OPEN = "already_open"  # Phase 2: a paper position in this ETF is already open
REASON_POSITION_LIMIT = "position_limit"  # Phase 2: MAX_OPEN_POSITIONS already held
REASON_COMPUTE_ERROR = "compute_error"
FILTER_REASONS = (
    REASON_NO_PRICE_DATA,
    REASON_INSUFFICIENT_HISTORY,
    REASON_DATA_QUALITY,
    REASON_ILLIQUID,
    REASON_NOT_LEADER,
    REASON_TREND_FAIL,
    REASON_STOP_TOO_WIDE,
    REASON_CORRELATED,
    REASON_SIZE_ZERO,
    REASON_SIGNAL_CAP,
    REASON_ALREADY_OPEN,
    REASON_POSITION_LIMIT,
    REASON_COMPUTE_ERROR,
)

# data_provenance / market_regime `data_freshness` values
FRESHNESS_FRESH = "fresh"
FRESHNESS_REFRESHED = "refreshed"  # cache was stale; a cache-bypassing refetch fixed it
FRESHNESS_STALE_ALLOWED = "stale_allowed"  # --allow-stale escape hatch
FRESHNESS_SYNTHETIC = "synthetic"  # --dry-run

# ETF-mode scans store the benchmark here (matches other ETF-mode rows).
SECTOR_ETF_COLUMN = "SPY"

# Placeholders only — set real values via SECTOR_SWING_EQUITY / --equity.
DEFAULT_EQUITY = 50_000.0
EQUITY_ENV = "SECTOR_SWING_EQUITY"

# Premarket cron scans the *prior* session; NYSE closes 16:00 ET, allow 15 min for the final bar.
SESSION_CLOSE_HOUR = 16
SESSION_CLOSE_MINUTE = 15


@dataclass(frozen=True)
class SwingParams:
    # H — hygiene
    min_bars: int = 210
    min_avg_dollar_volume: float = 20_000_000.0
    min_price: float = ETF_MIN_PRICE
    liquidity_window: int = 20
    # R2 — leadership (relative strength vs SPY)
    rs_short_days: int = 63
    rs_long_days: int = 126
    top_n_leaders: int = 4
    require_positive_rs: bool = True
    # R3 — trend
    ema_fast: int = 10
    ema_mid: int = 20
    sma_trend: int = 50
    adx_window: int = 14
    adx_min: float = 20.0
    # R4 / R5 — pullback and trigger
    pullback_lookback: int = 6
    pullback_tolerance: float = 1.005
    # R6 — stop
    atr_window: int = 14
    stop_atr_buffer: float = 0.25
    max_stop_atr: float = 2.5
    # R7 — sizing
    risk_pct: float = 0.01
    max_position_pct: float = 0.30
    # R8 — exit guidance (tracked in Phase 2)
    target_r: float = 2.0
    chase_atr: float = 0.5
    max_hold_days: int = 10
    trail_mode: str = "ema10"  # or "chandelier"
    chandelier_atr: float = 3.0
    # Portfolio gates
    max_new_signals: int = 3
    corr_window: int = 60
    corr_max: float = 0.85
    corr_min_overlap: int = 30
    # Phase 2 — open-position awareness
    max_open_positions: int = 3
    weekly_loss_limit_pct: float = 0.03  # advisory "trading paused" flag, never blocks plans
    # R1 — regime
    regime_fast_sma: int = 50
    regime_slow_sma: int = 200


DEFAULT_PARAMS = SwingParams()


def params_hash(params: SwingParams) -> str:
    """Stable short hash of the rule constants, recorded in data_provenance."""
    payload = json.dumps(asdict(params), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def resolve_equity(cli_value: float | None = None) -> float:
    """CLI value > SECTOR_SWING_EQUITY env > placeholder default."""
    if cli_value is not None:
        value = float(cli_value)
    else:
        raw = os.environ.get(EQUITY_ENV, "").strip()
        value = float(raw) if raw else DEFAULT_EQUITY
    if value <= 0:
        raise ValueError(f"Equity must be positive (got {value})")
    return value
