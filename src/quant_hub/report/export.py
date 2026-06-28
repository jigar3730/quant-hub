import json
from pathlib import Path


def export_json_report(report: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(report, f, indent=2, default=str)
    return path


def export_markdown_report(report: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = _render_markdown(report)
    path.write_text("\n".join(lines) + "\n")
    return path


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
        f"- **Regime:** {regime['label']} (multiplier {regime['multiplier']})",
        (
            f"- **SPY:** ${regime['spy_price']} | SMA50: ${regime['sma50']}"
            f" | SMA200: ${regime['sma200']}"
        ),
        (
            f"- **63d return:** {regime['return_63d_pct']}%"
            f" | **Below 52w high:** {regime['pct_below_52w_high']}%"
        ),
        f"- {regime['meaning']}",
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
