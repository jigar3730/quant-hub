"""Unit tests for forward-return label computation."""

from __future__ import annotations

from datetime import date

import pandas as pd

from quant_hub.ml.constants import (
    LABEL_STATUS_INSUFFICIENT_FUTURE,
    LABEL_STATUS_INVALID_ANCHOR,
    LABEL_STATUS_NO_PRICE,
    LABEL_STATUS_OK,
)
from quant_hub.ml.labels import (
    anchor_date_from_run,
    compute_forward_outcome,
)


def _price_df(closes: list[float], start: date) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=len(closes))
    return pd.DataFrame({"Date": dates, "Close": closes})


def test_compute_forward_outcome_basic():
    df = _price_df([100.0, 102.0, 104.0, 106.0, 108.0, 110.0], start=date(2026, 1, 1))
    anchor = date(2026, 1, 3)
    outcome = compute_forward_outcome(df, anchor_date=anchor, horizon_days=3)
    assert outcome.label_status == LABEL_STATUS_OK
    assert outcome.forward_return_pct == 3.8462
    assert outcome.label_binary is True
    assert outcome.forward_max_gain_pct >= outcome.forward_return_pct


def test_compute_forward_outcome_insufficient_future():
    df = _price_df([100.0, 101.0], start=date(2026, 1, 1))
    outcome = compute_forward_outcome(
        df, anchor_date=date(2026, 1, 1), horizon_days=5
    )
    assert outcome.label_status == LABEL_STATUS_INSUFFICIENT_FUTURE
    assert outcome.forward_return_pct is None


def test_compute_forward_outcome_invalid_anchor():
    df = _price_df([100.0, 101.0, 102.0], start=date(2026, 1, 1))
    outcome = compute_forward_outcome(
        df, anchor_date=date(2026, 1, 10), horizon_days=2
    )
    assert outcome.label_status == LABEL_STATUS_INVALID_ANCHOR


def test_compute_forward_outcome_no_price():
    outcome = compute_forward_outcome(None, anchor_date=date(2026, 1, 1), horizon_days=5)
    assert outcome.label_status == LABEL_STATUS_NO_PRICE


def test_compute_forward_outcome_spy_excess():
    stock = _price_df([100.0, 110.0, 120.0, 130.0], start=date(2026, 1, 1))
    spy = _price_df([100.0, 101.0, 102.0, 103.0], start=date(2026, 1, 1))
    anchor = date(2026, 1, 1)
    outcome = compute_forward_outcome(
        stock, anchor_date=anchor, horizon_days=3, spy_df=spy
    )
    assert outcome.label_status == LABEL_STATUS_OK
    assert outcome.spy_forward_return_pct == 1.9802
    assert outcome.excess_return_pct is not None
    assert outcome.excess_return_pct > 10


def test_anchor_date_from_run_provenance():
    run = {
        "scan_date": date(2026, 6, 1),
        "metadata": {"data_provenance": {"as_of_price": "2026-05-30"}},
    }
    assert anchor_date_from_run(run) == date(2026, 5, 30)


def test_anchor_date_from_run_fallback():
    run = {"scan_date": date(2026, 6, 1), "metadata": {}}
    assert anchor_date_from_run(run) == date(2026, 6, 1)
