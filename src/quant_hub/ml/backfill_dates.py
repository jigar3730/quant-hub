"""Weekly scan-date helpers for historical backfill."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def iter_weekly_scan_dates(since: date, until: date) -> list[date]:
    """Fridays from `since` through `until` (inclusive), aligned to week-ending Friday."""
    if since > until:
        return []
    current = since
    while current.weekday() != 4:
        current += timedelta(days=1)
        if current > until:
            return []
    dates: list[date] = []
    while current <= until:
        dates.append(current)
        current += timedelta(days=7)
    return dates


def truncate_weekly_to_date(df: pd.DataFrame | None, as_of: date) -> pd.DataFrame | None:
    """Keep weekly OHLCV rows on or before `as_of` (point-in-time, no lookahead)."""
    if df is None or df.empty or "Date" not in df.columns:
        return df
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Date"])
    trimmed = out[out["Date"].dt.date <= as_of]
    if trimmed.empty:
        return trimmed.reset_index(drop=True)
    return trimmed.reset_index(drop=True)
