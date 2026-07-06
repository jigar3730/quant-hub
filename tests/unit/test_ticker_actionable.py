from __future__ import annotations

from quant_hub.history.actionable import is_actionable


def test_breakout_actionable_tiers():
    assert is_actionable("breakout", tier="Tier 1")
    assert is_actionable("breakout", tier="Tier 2")
    assert not is_actionable("breakout", tier="Tier 3")
    assert not is_actionable("breakout", tier="filtered")


def test_swing_actionable_tiers():
    assert is_actionable("swing", tier="SETUP_LONG")
    assert is_actionable("swing", tier="SETUP_SHORT")
    assert not is_actionable("swing", tier="filtered")


def test_lynch_actionable_passed():
    assert is_actionable("lynch", tier="fast_grower", detail={"passed": True})
    assert is_actionable("lynch", tier="passed", eligible=True, detail={"passed": True})
    assert not is_actionable("lynch", tier="filtered", eligible=False, detail={"passed": False})


def test_mean_reversion_high_conviction_only():
    assert is_actionable("mean_reversion", tier="HIGH_CONVICTION")
    assert not is_actionable("mean_reversion", tier="WATCHLIST")
    assert not is_actionable("mean_reversion", tier="filtered")
