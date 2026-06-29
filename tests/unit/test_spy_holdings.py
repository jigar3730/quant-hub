"""Tests for SPY holdings fetch and universe refresh."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from quant_hub.application.universe_refresh import UniverseRefreshService
from quant_hub.data.spy_holdings import (
    MIN_EXPECTED_HOLDINGS,
    parse_spy_holdings_df,
    vendor_to_yahoo,
)
from quant_hub.universes.registry import UniverseRegistry


def _sample_holdings_df(count: int = MIN_EXPECTED_HOLDINGS) -> pd.DataFrame:
    rows = [{"Ticker": f"Z{i:04d}"} for i in range(count - 1)]
    rows.append({"Ticker": "BRK.B"})
    rows.append({"Ticker": "CASH_USD"})
    return pd.DataFrame(rows)


def test_vendor_to_yahoo_maps_class_shares():
    assert vendor_to_yahoo("brk.b") == "BRK-B"
    assert vendor_to_yahoo("BF.B") == "BF-B"


def test_parse_spy_holdings_df_filters_cash_and_normalizes():
    df = _sample_holdings_df()
    tickers = parse_spy_holdings_df(df)
    assert "BRK-B" in tickers
    assert "CASH_USD" not in tickers
    assert len(tickers) == MIN_EXPECTED_HOLDINGS


def test_parse_spy_holdings_df_skips_cusip_like_rows():
    rows = [{"Ticker": f"T{i:04d}"} for i in range(MIN_EXPECTED_HOLDINGS)]
    rows.extend([{"Ticker": "2602335D"}, {"Ticker": "CASH_USD"}])
    df = pd.DataFrame(rows)
    tickers = parse_spy_holdings_df(df)
    assert "2602335D" not in tickers
    assert len(tickers) == MIN_EXPECTED_HOLDINGS


def test_parse_spy_holdings_df_rejects_too_few():
    df = pd.DataFrame({"Ticker": ["AAPL", "MSFT", "CASH_USD"]})
    with pytest.raises(ValueError, match="parsed to"):
        parse_spy_holdings_df(df)


def test_sp500_index_universe_resolves_when_file_exists(tmp_path: Path):
    tickers_file = tmp_path / "sp500_index.txt"
    tickers_file.write_text("AAPL\nMSFT\nNVDA\n")
    config = {
        "universes": {
            "sp500_index": {
                "name": "S&P 500 (SPY holdings)",
                "sources": [{"type": "file", "path": str(tickers_file)}],
                "refresh": {"provider": "ssga_spy"},
            }
        }
    }
    config_path = tmp_path / "universes.json"
    config_path.write_text(__import__("json").dumps(config))
    reg = UniverseRegistry(config_path=config_path)
    assert reg.get_refresh_config("sp500_index") == {"provider": "ssga_spy"}
    assert reg.get_file_source_path("sp500_index") == tickers_file
    assert reg._resolve_id("sp500_index") == ["AAPL", "MSFT", "NVDA"]


def test_refresh_writes_file_and_meta(tmp_path: Path):
    tickers_file = tmp_path / "sp500_index.txt"
    config = {
        "universes": {
            "sp500_index": {
                "name": "S&P 500 (SPY holdings)",
                "sources": [{"type": "file", "path": str(tickers_file)}],
                "refresh": {"provider": "ssga_spy"},
            }
        }
    }
    config_path = tmp_path / "universes.json"
    config_path.write_text(__import__("json").dumps(config))
    reg = UniverseRegistry(config_path=config_path)
    service = UniverseRefreshService(registry=reg)

    sample = ["AAPL", "MSFT", "NVDA"] * 160  # 480 tickers

    def fake_refresh(output_path, *, url=None):
        from quant_hub.data.tickers import write_tickers_file

        write_tickers_file(output_path, sample)
        return sample

    with patch.dict(
        "quant_hub.application.universe_refresh.REFRESH_PROVIDERS",
        {"ssga_spy": fake_refresh},
    ):
        result = service.refresh("sp500_index")

    assert result.ticker_count == 480
    assert tickers_file.exists()
    meta = tmp_path / "sp500_index.meta.json"
    assert meta.exists()
    assert "refreshed_at" in meta.read_text()


def test_refresh_unknown_universe_raises():
    service = UniverseRefreshService()
    with pytest.raises(ValueError, match="Unknown universe"):
        service.refresh("not-a-universe")


def test_refresh_sp500_without_provider_raises():
    service = UniverseRefreshService()
    with pytest.raises(ValueError, match="no refresh provider"):
        service.refresh("sp500")


@pytest.mark.integration
def test_fetch_spy_holdings_live():
    from quant_hub.data.spy_holdings import fetch_spy_holdings

    tickers = fetch_spy_holdings()
    assert len(tickers) >= MIN_EXPECTED_HOLDINGS
    assert "AAPL" in tickers
    assert "BRK-B" in tickers or "BRK.B" not in tickers
