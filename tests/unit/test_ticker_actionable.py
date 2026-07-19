from __future__ import annotations

from quant_hub.history.actionable import is_actionable


def test_launchpad_actionable_tiers():
    assert is_actionable("launchpad", tier="Tier 1")
    assert is_actionable("launchpad", tier="Tier 2")
    assert not is_actionable("launchpad", tier="Tier 3")
    assert not is_actionable("launchpad", tier="filtered")


def test_lynch_actionable_passed():
    assert is_actionable("lynch", tier="fast_grower", detail={"passed": True})
    assert is_actionable("lynch", tier="passed", eligible=True, detail={"passed": True})
    assert not is_actionable("lynch", tier="filtered", eligible=False, detail={"passed": False})
