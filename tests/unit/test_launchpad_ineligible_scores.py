"""Ineligible Launchpad names still receive factor scores."""

from __future__ import annotations

import numpy as np
import pandas as pd

from quant_hub.config import BENCHMARK_TICKER
from quant_hub.engine.context import ScanContext
from quant_hub.engine.export import ticker_results_to_legacy_scores
from quant_hub.engine.runner import StrategyEngine
from quant_hub.report.builder import build_ticker_report
from quant_hub.scoring.launchpad import launchpad_eligibility_detail
from quant_hub.strategies.registry import get_strategy


def _ohlcv(ticker: str, close: np.ndarray, *, volume: float = 1_000_000) -> pd.DataFrame:
    dates = pd.bdate_range(end=pd.Timestamp.today(), periods=len(close))
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": [volume] * len(close),
            "ticker": ticker,
        }
    )


def _eligible_close() -> np.ndarray:
    return np.concatenate([np.linspace(40, 70, 220), np.full(40, 70.0)])


def _cheap_close() -> np.ndarray:
    return np.concatenate([np.linspace(4, 8, 220), np.full(40, 8.0)])


def _spy_close() -> np.ndarray:
    return np.concatenate([np.linspace(400, 500, 220), np.full(40, 500.0)])


def _scan_context() -> ScanContext:
    prices = pd.concat(
        [
            _ohlcv(BENCHMARK_TICKER, _spy_close()),
            _ohlcv("GOOD", _eligible_close()),
            _ohlcv("CHEAP", _cheap_close()),
        ],
        ignore_index=True,
    )
    return ScanContext.from_prices(prices, universe=["GOOD", "CHEAP"])


def test_engine_scores_ineligible_tickers():
    cheap_elig = launchpad_eligibility_detail(_ohlcv("CHEAP", _cheap_close()))
    assert cheap_elig["passed"] is False
    assert cheap_elig["fail_reason"] == "price_below_10"

    engine = StrategyEngine(get_strategy("launchpad"), context=_scan_context())
    result = engine.run()
    by_ticker = {t.ticker: t for t in result.tickers}

    cheap = by_ticker["CHEAP"]
    assert cheap.eligible is False
    assert cheap.filter_reason == "price_below_10"
    assert cheap.tier == "filtered"
    assert cheap.factors
    assert "squeeze_intensity" in cheap.factors
    assert cheap.final_score == cheap.normalized_score

    good = by_ticker["GOOD"]
    assert good.eligible is True
    assert good.factors
    assert good.final_score == good.normalized_score

    legacy = ticker_results_to_legacy_scores(result.tickers)
    assert "CHEAP" in legacy
    assert "squeeze_intensity_score" in legacy["CHEAP"]


def test_report_includes_scores_for_ineligible_ticker():
    cheap_df = _ohlcv("CHEAP", _cheap_close())
    spy_df = _ohlcv(BENCHMARK_TICKER, _spy_close())
    report = build_ticker_report(
        ticker="CHEAP",
        row={
            "ticker": "CHEAP",
            "eligible": False,
            "filter_reason": "price_below_10",
            "raw_score": 45.0,
            "normalized_score": 45.0,
            "regime_multiplier": 1.0,
            "final_adjusted_score": 45.0,
            "tier": "filtered",
        },
        stock_df=cheap_df,
        spy_df=spy_df,
        sector_df=None,
        sector_etf="XLF",
        fund={},
        scores={"squeeze_intensity_score": 25.0},
    )
    assert report["eligible"] is False
    assert report["scores"] is not None
    assert report["scores"]["squeeze_intensity"]["score"] == 25.0
    assert report["summary"]["final_adjusted_score"] == 45.0
    assert report["sector_etf"] == "XLF"
