"""Forward-return labels from cached daily OHLCV (no lookahead)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from quant_hub.config import LABEL_RETURN_THRESHOLD_PCT
from quant_hub.ml.constants import (
    LABEL_STATUS_INSUFFICIENT_FUTURE,
    LABEL_STATUS_INVALID_ANCHOR,
    LABEL_STATUS_NO_PRICE,
    LABEL_STATUS_OK,
)


@dataclass(frozen=True)
class OutcomeRow:
    horizon_days: int
    anchor_date: date
    forward_return_pct: float | None
    forward_max_gain_pct: float | None
    forward_max_drawdown_pct: float | None
    spy_forward_return_pct: float | None
    excess_return_pct: float | None
    label_binary: bool | None
    label_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_days": self.horizon_days,
            "anchor_date": self.anchor_date,
            "forward_return_pct": self.forward_return_pct,
            "forward_max_gain_pct": self.forward_max_gain_pct,
            "forward_max_drawdown_pct": self.forward_max_drawdown_pct,
            "spy_forward_return_pct": self.spy_forward_return_pct,
            "excess_return_pct": self.excess_return_pct,
            "label_binary": self.label_binary,
            "label_status": self.label_status,
        }


def parse_anchor_date(value: date | str | None, *, fallback: date) -> date | None:
    if value is None:
        return fallback
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def anchor_date_from_run(run: dict[str, Any]) -> date:
    """Resolve price anchor from provenance; default to scan_date."""
    metadata = run.get("metadata") or {}
    prov = metadata.get("data_provenance") or {}
    anchor = parse_anchor_date(prov.get("as_of_price"), fallback=run["scan_date"])
    if anchor is None:
        anchor = run["scan_date"]
    return anchor


def _forward_path_metrics(entry: float, path: pd.Series) -> tuple[float, float, float]:
    """Return (total_return_pct, max_gain_pct, max_drawdown_pct) along path."""
    if entry <= 0 or path.empty:
        return 0.0, 0.0, 0.0
    rel = path.astype(float) / entry
    total = (float(rel.iloc[-1]) - 1.0) * 100.0
    peak = float(rel.cummax().max())
    trough = float(rel.cummin().min())
    max_gain = (peak - 1.0) * 100.0
    max_drawdown = (trough - 1.0) * 100.0
    return total, max_gain, max_drawdown


def compute_forward_outcome(
    price_df: pd.DataFrame | None,
    *,
    anchor_date: date,
    horizon_days: int,
    spy_df: pd.DataFrame | None = None,
    return_threshold_pct: float = LABEL_RETURN_THRESHOLD_PCT,
) -> OutcomeRow:
    """
    Compute forward return using trading rows strictly after anchor_date.

    Entry = first close after anchor; exit = close horizon_days sessions later.
    """
    if price_df is None or price_df.empty or "Date" not in price_df.columns:
        return OutcomeRow(
            horizon_days=horizon_days,
            anchor_date=anchor_date,
            forward_return_pct=None,
            forward_max_gain_pct=None,
            forward_max_drawdown_pct=None,
            spy_forward_return_pct=None,
            excess_return_pct=None,
            label_binary=None,
            label_status=LABEL_STATUS_NO_PRICE,
        )

    df = price_df.copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    df = df.sort_values("Date")
    future = df[df["Date"] > anchor_date]
    if future.empty:
        return OutcomeRow(
            horizon_days=horizon_days,
            anchor_date=anchor_date,
            forward_return_pct=None,
            forward_max_gain_pct=None,
            forward_max_drawdown_pct=None,
            spy_forward_return_pct=None,
            excess_return_pct=None,
            label_binary=None,
            label_status=LABEL_STATUS_INVALID_ANCHOR,
        )

    if len(future) < horizon_days:
        return OutcomeRow(
            horizon_days=horizon_days,
            anchor_date=anchor_date,
            forward_return_pct=None,
            forward_max_gain_pct=None,
            forward_max_drawdown_pct=None,
            spy_forward_return_pct=None,
            excess_return_pct=None,
            label_binary=None,
            label_status=LABEL_STATUS_INSUFFICIENT_FUTURE,
        )

    path = future.iloc[:horizon_days]["Close"]
    entry = float(path.iloc[0])
    total, max_gain, max_drawdown = _forward_path_metrics(entry, path)

    spy_return: float | None = None
    excess: float | None = None
    if spy_df is not None and not spy_df.empty:
        spy_out = compute_forward_outcome(
            spy_df,
            anchor_date=anchor_date,
            horizon_days=horizon_days,
            return_threshold_pct=return_threshold_pct,
        )
        if spy_out.label_status == LABEL_STATUS_OK:
            spy_return = spy_out.forward_return_pct
            excess = total - float(spy_return)

    label_binary = total >= return_threshold_pct

    return OutcomeRow(
        horizon_days=horizon_days,
        anchor_date=anchor_date,
        forward_return_pct=round(total, 4),
        forward_max_gain_pct=round(max_gain, 4),
        forward_max_drawdown_pct=round(max_drawdown, 4),
        spy_forward_return_pct=round(spy_return, 4) if spy_return is not None else None,
        excess_return_pct=round(excess, 4) if excess is not None else None,
        label_binary=label_binary,
        label_status=LABEL_STATUS_OK,
    )
