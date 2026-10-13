"""Unit tests for the yfinance price download chunking."""

from __future__ import annotations

import pandas as pd
import pytest

from quant_hub.infrastructure.cache.parquet_cache import OHLCV_COLUMNS
from quant_hub.infrastructure.market import yfinance_prices


def test_download_chunk_returns_empty_frame_on_failure(monkeypatch):
    def _raise(*args, **kwargs):
        raise TimeoutError("yfinance timed out")

    monkeypatch.setattr(yfinance_prices.yf, "download", _raise)

    result = yfinance_prices._download_chunk(["AAPL"], "2026-01-01")

    assert isinstance(result, pd.DataFrame)
    assert result.empty
    assert list(result.columns) == ["Date", *OHLCV_COLUMNS, "ticker"]


def test_download_chunk_passes_timeout_to_yf_download(monkeypatch):
    captured = {}

    def _fake_download(tickers, **kwargs):
        captured.update(kwargs)
        return pd.DataFrame()

    monkeypatch.setattr(yfinance_prices.yf, "download", _fake_download)

    yfinance_prices._download_chunk(["AAPL"], "2026-01-01")

    assert captured.get("timeout") == 30
