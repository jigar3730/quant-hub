import pandas as pd
import pytest

from quant_hub.config import MAX_REASONABLE_GROWTH
from quant_hub.data.fundamentals.compute import (
    apply_growth_cap,
    eps_combined_growth,
    revenue_yoy_blended,
    ttm_yoy,
    yoy_quarterly,
)


def test_yoy_standard_positive_base():
    series = pd.Series([100.0, 101.0, 102.0, 103.0, 110.0])
    val, status = yoy_quarterly(series)
    assert status == "OK"
    assert val == pytest.approx(0.10, rel=1e-3)


def test_yoy_turnaround_loss_to_profit():
    series = pd.Series([-1.0, -0.5, -0.2, 0.1, 0.2, 0.5])
    val, status = yoy_quarterly(series)
    assert status == "OK"
    assert val == pytest.approx(0.50)


def test_yoy_loss_narrowing():
    series = pd.Series([-2.0, -1.8, -1.5, -1.2, -1.0, -0.8])
    val, status = yoy_quarterly(series)
    assert status == "OK"
    assert val is not None and val > 0


def test_ttm_yoy_eight_quarters():
    series = pd.Series([0.5, 0.5, 0.5, 0.5, 1.0, 2.0, 3.0, 4.0])
    val, status = ttm_yoy(series)
    assert status == "CAPPED"
    assert val == MAX_REASONABLE_GROWTH


def test_apply_growth_cap_hypergrowth():
    val, status = apply_growth_cap(5.0)
    assert status == "CAPPED"
    assert val == MAX_REASONABLE_GROWTH


def test_eps_combined_uses_operating_income_fallback():
    eps = pd.Series(dtype=float)
    op = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0])
    combined, status, _, _, source = eps_combined_growth(eps, operating_income=op)
    assert combined is not None
    assert status == "OK"
    assert source == "operating_income_ttm"


def test_revenue_yoy_blended():
    series = pd.Series([100.0, 105.0, 110.0, 115.0, 120.0, 130.0])
    val, status, source = revenue_yoy_blended(series)
    assert status == "OK"
    assert val is not None
    assert source in ("single_quarter_yoy", "two_quarter_yoy_avg")
