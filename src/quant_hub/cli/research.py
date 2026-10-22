"""quant-research — research datasets for backtests (kept apart from production caches)."""

from __future__ import annotations

import argparse

from quant_hub.application.research_data_service import ResearchDataService
from quant_hub.config import RESEARCH_DIR
from quant_hub.logging_setup import setup_logging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Research datasets")
    sub = parser.add_subparsers(dest="command", required=True)

    warm = sub.add_parser(
        "warm-history",
        help="Download ~20y daily history for sector ETFs, benchmarks, and VIX/TNX",
    )
    warm.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore the research cache and refetch everything",
    )

    args = parser.parse_args(argv)
    setup_logging("research.log")

    if args.command == "warm-history":
        coverage = ResearchDataService().warm_etf_history(force_refresh=args.force_refresh)
        RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        out = RESEARCH_DIR / "coverage.csv"
        coverage.to_csv(out, index=False)
        print(coverage.to_string(index=False))
        missing = coverage[coverage["bars"] == 0]["ticker"].tolist()
        print(f"\n{len(coverage)} tickers, {len(missing)} missing -> {out}")
        if missing:
            print(f"missing: {', '.join(missing)}")
            return 1
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
