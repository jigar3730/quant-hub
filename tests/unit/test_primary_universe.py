"""Primary S&P universe constant and registry invariants."""

from quant_hub.config import PRIMARY_INDEX_UNIVERSE
from quant_hub.digest import policy as P
from quant_hub.universes.registry import UniverseRegistry


def test_primary_index_universe_constant():
    assert PRIMARY_INDEX_UNIVERSE == "sp500_index"


def test_digest_policy_uses_primary_index():
    assert P.DAILY_BREAKOUT_UNIVERSE == PRIMARY_INDEX_UNIVERSE
    assert P.WEEKLY_SWING_UNIVERSE == PRIMARY_INDEX_UNIVERSE
    assert P.WEEKLY_LYNCH_UNIVERSE == PRIMARY_INDEX_UNIVERSE


def test_sp500_not_in_universe_registry():
    reg = UniverseRegistry()
    assert "sp500" not in reg.list_universes()
    assert PRIMARY_INDEX_UNIVERSE in reg.list_universes()
