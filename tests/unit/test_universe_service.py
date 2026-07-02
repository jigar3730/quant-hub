"""Universe resolution — CLI ticker override must win over universe_id."""

from quant_hub.application.universe_service import UniverseService


def test_ticker_override_wins_over_universe_id():
    svc = UniverseService()
    uid, tickers = svc.resolve(
        universe_id="sp500_index",
        tickers=["AAPL", "MSFT"],
    )
    assert uid == "sp500_index"
    assert tickers == ["AAPL", "MSFT"]
