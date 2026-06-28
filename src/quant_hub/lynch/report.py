"""Export Peter Lynch scan reports."""

from __future__ import annotations

from pathlib import Path

from quant_hub.lynch.categories import QUALITATIVE_OVERLAY
from quant_hub.serialization.json_util import json_dump_file


def export_json(report: dict, path: Path) -> None:
    json_dump_file(report, path)


def export_markdown(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = report["scan_summary"]
    lines = [
        "# Peter Lynch Scan Report",
        "",
        f"- **Preset:** {summary['preset_label']}",
        f"- **Universe:** {summary['universe_size']} tickers",
        f"- **Passed screen:** {summary['passed_count']}",
        f"- **Fast growers:** {summary['category_counts']['fast_grower']}",
        f"- **Stalwarts:** {summary['category_counts']['stalwart']}",
        f"- **Asset plays:** {summary['category_counts']['asset_play']}",
        "",
        "## Top Candidates",
        "",
    ]

    for t in report["candidates"][:25]:
        cats = ", ".join(t.get("categories", [])) or "base"
        lines.append(f"### {t['ticker']} — score {t['lynch_score']:.0f} ({cats})")
        if t.get("investor_summary"):
            lines.append(f"\n{t['investor_summary']}\n")
        m = t.get("metrics", {})
        lines.append(
            f"- P/E {m.get('pe_ratio')}, PEG {m.get('peg_ratio')}, "
            f"EPS growth 5Y {_fmt_pct(m.get('eps_growth_5y'))}, "
            f"D/E {_fmt_pct(m.get('debt_to_equity'))}"
        )
        if t.get("tier_reason"):
            lines.append(f"- {t['tier_reason']}")
        lines.append("")

    lines.extend(["## Qualitative Overlay (manual review)", ""])
    for note in QUALITATIVE_OVERLAY:
        lines.append(f"- {note}")
    lines.append("")

    path.write_text("\n".join(lines))


def _fmt_pct(value) -> str:
    if value is None:
        return "—"
    v = float(value)
    if abs(v) <= 1.5:
        return f"{v * 100:.1f}%"
    return f"{v:.1f}%"
