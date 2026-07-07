"""Dashboard styling and chart defaults.

All colors, spacing, and type sizing here are read from
`design_tokens.py` — the single source of truth for the visual language.
Do not reintroduce raw hex or ad hoc rem values in this file; add a token
instead so the whole dashboard stays consistent (and dark-mode-ready).
"""

from quant_hub.dashboard.viz.design_tokens import COLORS, CSS_VARS, TIER_BADGE_CSS

PLOTLY_CONFIG = {
    "displayModeBar": False,
    "scrollZoom": False,
}

PLOTLY_LAYOUT = {
    "template": "plotly_white",
    "font": {"family": "system-ui, sans-serif", "size": 12, "color": COLORS["text_secondary"]},
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "margin": {"l": 24, "r": 24, "t": 48, "b": 24},
    "title": {"font": {"size": 14, "color": COLORS["text_primary"]}},
}

# TIER_BADGE_CSS is imported above and re-exported here for callers that still
# do `from quant_hub.dashboard.viz.styles import TIER_BADGE_CSS` (e.g. components.py).

CUSTOM_CSS = f"""
<style>
{CSS_VARS}

    .block-container {{ padding-top: var(--space-lg); max-width: 1400px; }}

    .scan-header {{
        background: linear-gradient(135deg, var(--color-banner-start) 0%, var(--color-banner-end) 100%);
        color: var(--color-text-on-dark);
        padding: var(--space-lg) var(--space-xl);
        border-radius: 12px;
        margin-bottom: var(--space-lg);
    }}
    .scan-header h1 {{
        color: var(--color-text-on-dark) !important;
        margin: 0;
        font-size: var(--font-size-2xl);
        font-weight: var(--font-weight-2xl);
        line-height: var(--line-height-2xl);
    }}
    .scan-header p {{
        color: var(--color-text-on-dark-muted);
        margin: var(--space-xs) 0 0 0;
        font-size: var(--font-size-base);
        line-height: var(--line-height-base);
    }}

    .info-card {{
        background: var(--color-bg-canvas);
        border: 1px solid var(--color-border);
        border-radius: 10px;
        padding: var(--space-lg);
        margin-bottom: var(--space-md);
    }}
    .info-card h4 {{
        margin: 0 0 var(--space-sm) 0;
        color: var(--color-text-primary);
        font-size: var(--font-size-lg);
        font-weight: var(--font-weight-lg);
        line-height: var(--line-height-lg);
    }}

    .takeaway-card {{
        border-radius: 10px;
        padding: var(--space-md) var(--space-lg);
        margin-bottom: var(--space-md);
    }}

    .scan-as-of {{
        background: var(--color-primary-soft);
        border: 1px solid var(--color-primary-border);
        border-radius: 8px;
        padding: var(--space-sm) var(--space-md);
        margin-bottom: var(--space-md);
        font-size: var(--font-size-base);
        line-height: var(--line-height-base);
        color: var(--color-text-primary);
    }}

    .live-data-label {{
        color: var(--color-text-muted);
        font-size: var(--font-size-sm);
        line-height: var(--line-height-sm);
        margin-top: var(--space-sm);
    }}

    .tier-badge {{
        display: inline-block;
        padding: var(--space-xs) var(--space-md);
        border-radius: 999px;
        font-size: var(--font-size-sm);
        font-weight: 600;
    }}

    .pass-badge {{ color: var(--color-success-text); font-weight: 600; }}
    .fail-badge {{ color: var(--color-danger-text); font-weight: 600; }}

    .component-card {{
        background: var(--color-bg-surface);
        border: 1px solid var(--color-border);
        border-radius: 8px;
        padding: var(--space-md) var(--space-lg);
        margin-bottom: var(--space-sm);
    }}

    div[data-testid="stMetric"] {{
        background: var(--color-bg-canvas);
        border: 1px solid var(--color-border);
        border-radius: 10px;
        padding: var(--space-md) var(--space-lg);
    }}

    a.ticker-link {{
        color: var(--color-primary);
        font-weight: 600;
        text-decoration: none;
    }}
    a.ticker-link:hover {{
        text-decoration: underline;
        color: var(--color-primary-hover);
    }}
</style>
"""
