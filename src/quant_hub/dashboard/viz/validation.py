"""Detect reports that contain synthetic or stale test data."""

from __future__ import annotations

# SPY has traded well above this level since 2020; values below imply dry-run data.
SPY_MIN_REALISTIC_PRICE = 400.0


def regime_looks_synthetic(regime: dict) -> bool:
    price = regime.get("spy_price")
    if price is None:
        return False
    try:
        return float(price) < SPY_MIN_REALISTIC_PRICE
    except (TypeError, ValueError):
        return False
