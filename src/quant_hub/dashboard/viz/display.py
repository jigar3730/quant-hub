"""Format values for Streamlit dataframe display (Arrow-safe)."""

from __future__ import annotations

import json
from typing import Any


def format_display_value(value: Any) -> str:
    """Convert arbitrary metric/check values to a display string."""
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, default=str)
    if isinstance(value, float):
        if value != value:  # NaN
            return "—"
        if abs(value) < 1.5 and value not in (0.0, -0.0):
            return f"{value * 100:.2f}%"
        return f"{value:.4g}"
    return str(value)
