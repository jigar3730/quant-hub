import shutil
from pathlib import Path

from quant_hub.serialization.json_util import json_dump_file


def export_json_report(report: dict, path: Path) -> Path:
    json_dump_file(report, path)
    return path


def export_markdown_report(report: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = _render_markdown(report)
    path.write_text("\n".join(lines) + "\n")
    return path


def copy_to_legacy(path: Path, legacy_path: Path) -> None:
    if path.resolve() == legacy_path.resolve():
        return
    if path.exists():
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, legacy_path)


def _regime_line(regime: dict) -> list[str]:
    """Render regime section; supports breakout SPY and swing weekly contexts."""
    if regime.get("interval") == "1wk":
        return [
            f"- **Mode:** Weekly swing ({regime.get('period', '10y')} history)",
            f"- **Interval:** {regime.get('interval')}",
        ]
    spy = regime.get("spy_price")
    sma50 = regime.get("sma50")
    sma200 = regime.get("sma200")
    lines = [
        f"- **Regime:** {regime.get('label', 'unknown')} (multiplier {regime.get('multiplier', 1.0)})",
    ]
    if spy is not None:
        parts = [f"**SPY:** ${spy}"]
        if sma50 is not None:
            parts.append(f"SMA50: ${sma50}")
        if sma200 is not None:
            parts.append(f"SMA200: ${sma200}")
        lines.append(f"- {' | '.join(parts)}")
    ret = regime.get("return_63d_pct")
    below = regime.get("pct_below_52w_high")
    if ret is not None or below is not None:
        ret_s = f"{ret}%" if ret is not None else "—"
        below_s = f"{below}%" if below is not None else "—"
        lines.append(f"- **63d return:** {ret_s} | **Below 52w high:** {below_s}")
    meaning = regime.get("meaning")
    if meaning:
        lines.append(f"- {meaning}")
    return lines


def _render_markdown(report: dict) -> list[str]:
    summary = report["scan_summary"]
    regime = report["market_regime"]
    strategy_id = report.get("strategy_id", "breakout")
    title = {
        "swing": "Swing Pullback Scan Report",
        "breakout": "Breakout Scan Report",
    }.get(strategy_id, f"{strategy_id.title()} Scan Report")
    tier_line = " | ".join(
        f"{name}: {count}" for name, count in summary["tier_counts"].items()
    )
    lines = [
        f"# {title}",
        "",
        "## Market Regime",
        "",
        *_regime_line(regime),
        "",
        "## Scan Summary",
        "",
        f"- Universe: {summary['universe_size']} tickers",
        f"- Eligible: {summary['eligible_count']} | Excluded: {summary['excluded_count']}",
        f"- {tier_line}",
        "",
    ]

    if summary["filter_breakdown"]:
        lines.append("### Exclusion Breakdown")
        lines.append("")
        for reason, count in sorted(summary["filter_breakdown"].items(), key=lambda x: -x[1]):
            lines.append(f"- {reason}: {count}")
        lines.append("")

    eligible = [t for t in report["tickers"] if t["eligible"]]
    eligible.sort(key=lambda t: t["summary"]["final_adjusted_score"], reverse=True)

    lines.append("## Top Eligible Candidates")
    lines.append("")
    for t in eligible[:15]:
        s = t["summary"]
        lines.append(f"### {t['ticker']} — {t['tier']} (score {s['final_adjusted_score']})")
        lines.append("")
        lines.append(f"**{t['tier_reason']}**")
        lines.append("")
        if t["scores"]:
            for name, comp in t["scores"].items():
                label = name.replace("_", " ").title()
                lines.append(f"- **{label}** ({comp['score']}/{comp['max']}): {comp['meaning']}")
        lines.append("")

    excluded = [t for t in report["tickers"] if not t["eligible"]]
    if excluded:
        lines.append("## Excluded Tickers")
        lines.append("")
        for t in sorted(excluded, key=lambda x: x["ticker"]):
            lines.append(f"- **{t['ticker']}**: {t['tier_reason']}")
            failed = next(
                (c for c in t["eligibility"].get("checks", []) if not c.get("passed")),
                None,
            )
            if failed:
                detail = failed.get("detail") or failed.get("value")
                if detail:
                    lines.append(f"  - Failed `{failed['rule']}`: {detail}")
        lines.append("")

    return lines
