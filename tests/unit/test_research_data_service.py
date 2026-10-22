"""Research history warm-up: ticker assembly and coverage table (no network)."""

from __future__ import annotations

import pandas as pd

from quant_hub.application.research_data_service import (
    ResearchDataService,
    coverage_table,
)
from quant_hub.config import (
    RESEARCH_BENCHMARKS,
    RESEARCH_CONTEXT_SERIES,
    RESEARCH_ETF_UNIVERSE,
    RESEARCH_LOOKBACK_DAYS,
)


class _FakeUniverses:
    def __init__(self, tickers: list[str]) -> None:
        self.tickers = tickers
        self.requested: list[str] = []

    def resolve(self, *, universe_id: str):
        self.requested.append(universe_id)
        return universe_id, self.tickers


def _bars(ticker: str, start: str, n: int, nan_last: bool = False) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=n)
    close = [100.0 + i for i in range(n)]
    if nan_last:
        close[-1] = float("nan")
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close,
            "Low": close,
            "Close": close,
            "Volume": 1_000,
            "ticker": ticker,
        }
    )


def test_etf_tickers_add_benchmarks_and_context_without_duplicates():
    universes = _FakeUniverses(["XLK", "SPY", "XLE"])
    service = ResearchDataService(universe_service=universes, cache=object())

    tickers = service.etf_tickers()

    assert universes.requested == [RESEARCH_ETF_UNIVERSE]
    assert tickers == sorted(tickers)
    assert len(tickers) == len(set(tickers))
    assert {"XLK", "XLE", *RESEARCH_BENCHMARKS, *RESEARCH_CONTEXT_SERIES} == set(tickers)


def test_warm_passes_long_lookback_and_research_cache():
    calls = {}
    cache = object()

    def fake_download(tickers, *, use_cache, lookback_days, cache):
        calls.update(tickers=tickers, use_cache=use_cache, lookback=lookback_days, cache=cache)
        return pd.concat([_bars(t, "2006-01-02", 5) for t in tickers], ignore_index=True)

    service = ResearchDataService(
        universe_service=_FakeUniverses(["XLK"]), downloader=fake_download, cache=cache
    )
    coverage = service.warm_etf_history(force_refresh=True)

    assert calls["lookback"] == RESEARCH_LOOKBACK_DAYS
    assert calls["use_cache"] is False
    assert calls["cache"] is cache
    assert (coverage["bars"] == 5).all()


def test_coverage_table_reports_missing_and_nan_share():
    prices = pd.concat(
        [_bars("SPY", "2006-01-02", 4), _bars("XLC", "2018-06-19", 2, nan_last=True)],
        ignore_index=True,
    )

    cov = coverage_table(prices, ["SPY", "XLC", "FDIG"]).set_index("ticker")

    assert cov.loc["SPY", "bars"] == 4
    assert str(cov.loc["SPY", "first_date"]) == "2006-01-02"
    assert cov.loc["XLC", "nan_close_share"] == 0.5
    assert cov.loc["FDIG", "bars"] == 0
    assert pd.isna(cov.loc["FDIG", "first_date"])


def test_coverage_table_handles_empty_download():
    empty = pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume", "ticker"])

    cov = coverage_table(empty, ["SPY"])

    assert cov["bars"].tolist() == [0]
