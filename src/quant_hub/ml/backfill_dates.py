"""Daily-price scan-date helpers for Launchpad historical backfill."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd


def as_scan_date(value: date | datetime | str | None) -> date | None:
    """Normalize Postgres / CLI values to plain scan dates."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@dataclass
class BackfillCoverage:
    since: date
    until: date
    planned_dates: list[date]
    existing_dates: set[date] = field(default_factory=set)

    @property
    def missing_dates(self) -> list[date]:
        existing = self.existing_dates
        return [d for d in self.planned_dates if d not in existing]

    @property
    def earliest_planned(self) -> date | None:
        return self.planned_dates[0] if self.planned_dates else None

    @property
    def latest_planned(self) -> date | None:
        return self.planned_dates[-1] if self.planned_dates else None

    @property
    def earliest_existing(self) -> date | None:
        return min(self.existing_dates) if self.existing_dates else None

    @property
    def latest_existing(self) -> date | None:
        return max(self.existing_dates) if self.existing_dates else None

    def summary(self) -> str:
        return (
            f"range={self.earliest_planned}..{self.latest_planned} "
            f"planned={len(self.planned_dates)} existing={len(self.existing_dates)} "
            f"missing={len(self.missing_dates)}"
        )

    def detail_lines(self, *, missing_preview: int = 5) -> list[str]:
        lines = [self.summary()]
        if self.earliest_existing:
            lines.append(
                f"db_range={self.earliest_existing}..{self.latest_existing} "
                f"({len(self.existing_dates)} Saturdays in range)"
            )
        else:
            lines.append("db_range=empty (no scan_runs in requested window)")
        missing = self.missing_dates
        if missing:
            preview = ", ".join(str(d) for d in missing[:missing_preview])
            suffix = f" ... +{len(missing) - missing_preview} more" if len(missing) > missing_preview else ""
            lines.append(f"first_missing=[{preview}{suffix}]")
        return lines


def compute_backfill_coverage(
    *,
    since: date,
    until: date,
    existing_dates: list[date] | set[date] | None = None,
) -> BackfillCoverage:
    planned = iter_saturday_scan_dates(since, until)
    existing = {as_scan_date(d) for d in (existing_dates or []) if as_scan_date(d) is not None}
    return BackfillCoverage(
        since=since,
        until=until,
        planned_dates=planned,
        existing_dates=existing,
    )


def truncate_daily_to_date(df: pd.DataFrame | None, as_of: date) -> pd.DataFrame | None:
    """Keep daily OHLCV rows on or before `as_of` (point-in-time, no lookahead)."""
    if df is None or df.empty or "Date" not in df.columns:
        return df
    out = df.copy()
    out["Date"] = pd.to_datetime(out["Date"])
    return out[out["Date"].dt.date <= as_of].reset_index(drop=True)


def iter_saturday_scan_dates(since: date, until: date) -> list[date]:
    """Saturdays from `since` through `until` (inclusive)."""
    if since > until:
        return []
    current = since
    while current.weekday() != 5:
        current += timedelta(days=1)
        if current > until:
            return []
    dates: list[date] = []
    while current <= until:
        dates.append(current)
        current += timedelta(days=7)
    return dates


def earliest_daily_backfill_supported(
    *,
    today: date | None = None,
    min_daily_bars: int = 200,
    lookback_days: int = 1260,
) -> date:
    """Earliest scan_date with enough truncated daily history for Launchpad."""
    today = today or date.today()
    calendar_span = int(lookback_days * 1.6)
    return today - timedelta(days=max(calendar_span - min_daily_bars, min_daily_bars))
