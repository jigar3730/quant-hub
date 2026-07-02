"""Lynch scan service behavior."""

import inspect

from quant_hub.application import lynch_service as lynch_module


def test_lynch_service_does_not_copy_legacy_files():
    assert "copy_to_legacy" not in inspect.getsource(lynch_module)
