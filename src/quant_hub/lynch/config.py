"""Peter Lynch scanner thresholds and presets."""

from __future__ import annotations

PEG_MAX = 1.2
PEG_BARGAIN = 0.5
EPS_GROWTH_MIN = 0.10
EPS_GROWTH_MAX = 0.50
PE_MAX = 25.0
DEBT_TO_EQUITY_MAX = 0.50
INSTITUTIONAL_OWNERSHIP_MAX = 0.65
ANALYST_COVERAGE_MAX = 8
ROE_MIN_ANTI = 0.08
REVENUE_CV_MAX = 0.75

FAST_GROWER_MCAP_MAX = 10_000_000_000
FAST_GROWER_EPS_GROWTH_MIN = 0.15
FAST_GROWER_PEG_MAX = 1.2
FAST_GROWER_DE_MAX = 0.40

STALWART_MCAP_MIN = 10_000_000_000
STALWART_PE_MAX = 22.0
STALWART_EPS_GROWTH_MIN = 0.08
STALWART_EPS_GROWTH_MAX = 0.18
STALWART_DIVIDEND_YIELD_MIN = 0.012

ASSET_PLAY_PB_MAX = 1.0
ASSET_PLAY_NET_CASH_PRICE_MIN = 0.30

PRESETS = ("base", "fast_grower", "stalwart", "asset_play", "summary")

PRESET_LABELS = {
    "base": "Lynch Base Screen",
    "fast_grower": "Fast Growers (10-Bagger Hunt)",
    "stalwart": "Stalwarts (Portfolio Anchors)",
    "asset_play": "Asset Plays (Deep Value)",
    "summary": "Full Lynch Scan (all categories)",
}

CATEGORY_LABELS = {
    "fast_grower": "Fast Grower",
    "stalwart": "Stalwart",
    "asset_play": "Asset Play",
    "base": "Base screen",
}
