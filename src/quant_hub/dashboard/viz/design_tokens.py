"""Design tokens — single source of truth for dashboard color, spacing, and type.

Visual direction: clean, minimal, dark-mode-friendly. Low-chrome surfaces,
a strict spacing scale, a restrained type scale, and one confident primary
accent (indigo) instead of scattering the same blue across links, charts,
badges, and buttons.

Shipping light mode only for now — Streamlit itself is on a light base theme
(see `.streamlit/config.toml`). Every color below is a *semantic* token
(`bg_surface`, `text_secondary`, `success_bg`, ...) rather than a raw hex
reused ad hoc, so a future dark theme is a matter of swapping the values in
`COLORS` (or layering a `[data-theme="dark"]` override on `CSS_VARS`) instead
of hunting through every component file.
"""

from __future__ import annotations

COLORS: dict[str, str] = {
    # Canvas / surfaces
    "bg_canvas": "#f8fafc",
    "bg_surface": "#ffffff",
    "bg_elevated": "#f1f5f9",
    "border": "#e2e8f0",
    "border_strong": "#cbd5e1",
    # Text
    "text_primary": "#0f172a",
    "text_secondary": "#475569",
    "text_muted": "#94a3b8",
    "text_on_primary": "#ffffff",
    "text_on_dark": "#f8fafc",
    "text_on_dark_muted": "#cbd5e1",
    # Primary accent (indigo) — replaces the generic sky-blue used everywhere before
    "primary": "#4f46e5",
    "primary_hover": "#4338ca",
    "primary_soft": "#eef2ff",
    "primary_border": "#c7d2fe",
    # Header banner (dark surface, independent of the light canvas)
    "banner_start": "#0f172a",
    "banner_end": "#312e81",
    # Semantic triads (background / text / border) used for badges, alerts, banners
    "success_bg": "#dcfce7",
    "success_text": "#166534",
    "success_border": "#bbf7d0",
    "success_solid": "#22c55e",
    "warning_bg": "#fef9c3",
    "warning_text": "#854d0e",
    "warning_border": "#fde68a",
    "warning_solid": "#eab308",
    "danger_bg": "#fee2e2",
    "danger_text": "#991b1b",
    "danger_border": "#fecaca",
    "danger_solid": "#ef4444",
    "danger_on_dark": "#fca5a5",
    "neutral_bg": "#f1f5f9",
    "neutral_text": "#475569",
    "neutral_border": "#e2e8f0",
    "neutral_solid": "#94a3b8",
    # Extra categorical accent for charts needing a distinct 3rd/4th hue
    "accent_violet": "#a855f7",
}

# Strict 8px-family spacing scale (px). Replaces ad hoc values like
# 1.1rem / 0.85rem / 0.15rem scattered through the old CUSTOM_CSS.
SPACING: dict[str, int] = {
    "xs": 4,
    "sm": 8,
    "md": 12,
    "lg": 16,
    "xl": 24,
    "2xl": 32,
    "3xl": 48,
    "4xl": 64,
}


def _rem(px: int) -> str:
    value = px / 16
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{text}rem"


SPACING_REM: dict[str, str] = {key: _rem(px) for key, px in SPACING.items()}

# Named type steps: {size (px), weight, line_height (px)}.
TYPE_SCALE: dict[str, dict[str, int]] = {
    "xs": {"size": 11, "weight": 500, "line_height": 16},
    "sm": {"size": 12, "weight": 400, "line_height": 18},
    "base": {"size": 13, "weight": 400, "line_height": 20},
    "md": {"size": 14, "weight": 500, "line_height": 22},
    "lg": {"size": 16, "weight": 600, "line_height": 24},
    "xl": {"size": 20, "weight": 600, "line_height": 28},
    "2xl": {"size": 24, "weight": 700, "line_height": 32},
}


def _build_css_vars() -> str:
    lines = [":root {"]
    for key, value in COLORS.items():
        lines.append(f"  --color-{key.replace('_', '-')}: {value};")
    for key, value in SPACING_REM.items():
        lines.append(f"  --space-{key}: {value};")
    for key, step in TYPE_SCALE.items():
        lines.append(f"  --font-size-{key}: {step['size']}px;")
        lines.append(f"  --font-weight-{key}: {step['weight']};")
        lines.append(f"  --line-height-{key}: {step['line_height']}px;")
    lines.append("}")
    return "\n".join(lines)


CSS_VARS: str = _build_css_vars()

# Tier/status -> semantic triad mapping, shared by badges (HTML) and charts (solid hex).
TIER_SEMANTIC: dict[str, str] = {
    "Tier 1": "success",
    "Tier 2": "warning",
    "Tier 3": "neutral",
    "filtered": "danger",
}

TIER_COLORS: dict[str, str] = {
    tier: COLORS[f"{kind}_solid"] for tier, kind in TIER_SEMANTIC.items()
}

TIER_BADGE_CSS: dict[str, str] = {
    tier: f"background:{COLORS[f'{kind}_bg']};color:{COLORS[f'{kind}_text']};"
    for tier, kind in TIER_SEMANTIC.items()
}

# Peter Lynch category colors, drawn from the same semantic palette.
LYNCH_CATEGORY_COLORS: dict[str, str] = {
    "fast_grower": COLORS["success_solid"],
    "stalwart": COLORS["primary"],
    "asset_play": COLORS["accent_violet"],
    "base": COLORS["neutral_solid"],
}

# Small categorical sequence for multi-series charts (compare radar, etc).
CHART_PALETTE: list[str] = [COLORS["primary"], COLORS["warning_solid"], COLORS["success_solid"]]
