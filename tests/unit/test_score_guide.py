"""Tests for score component cheat sheet."""

from quant_hub.dashboard.viz.data import SCORE_LABELS
from quant_hub.dashboard.viz.score_guide import COMPONENT_HELP, SCORE_GUIDE_SECTIONS


def test_component_help_covers_all_score_labels():
    keys = set(SCORE_LABELS.keys())
    assert keys == set(COMPONENT_HELP.keys())


def test_score_guide_has_four_sections():
    assert len(SCORE_GUIDE_SECTIONS) == 4
    assert SCORE_GUIDE_SECTIONS[0].title.startswith("1. Market Momentum")
