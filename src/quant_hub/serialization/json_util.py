"""JSON helpers safe for Postgres jsonb and file exports."""

from __future__ import annotations

import json
import math
from typing import Any


def sanitize_for_json(value: Any) -> Any:
    """Replace NaN/Inf floats so output is valid JSON for Postgres and analysts."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_json(v) for v in value]
    return value


def json_dumps(value: Any) -> str:
    return json.dumps(sanitize_for_json(value))


def json_dump_file(value: Any, path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(sanitize_for_json(value), f, indent=2, default=str)
