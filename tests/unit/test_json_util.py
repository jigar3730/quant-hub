import json

from quant_hub.serialization.json_util import json_dumps, sanitize_for_json


def test_sanitize_nan_and_inf():
    data = {"x": float("nan"), "y": float("inf"), "z": 1.0}
    clean = sanitize_for_json(data)
    assert clean["x"] is None
    assert clean["y"] is None
    assert clean["z"] == 1.0


def test_json_dumps_valid_for_postgres():
    raw = json_dumps({"eps": float("nan")})
    parsed = json.loads(raw)
    assert parsed["eps"] is None
