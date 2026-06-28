"""quant-scan — run a breakout scan."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from quant_hub.application.scan_service import ScanService
from quant_hub.config import DEFAULT_OUTPUT_CSV, DEFAULT_OUTPUT_JSON, DEFAULT_OUTPUT_MD
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run breakout scan")
    parser.add_argument("--universe", help="Named universe id (e.g. sp500)")
    parser.add_argument("--tickers", nargs="+", help="Explicit ticker list")
    parser.add_argument("--tickers-file", type=Path, help="Path to ticker file")
    parser.add_argument("--cache", action="store_true", help="Use parquet price cache")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache")
    parser.add_argument("--dry-run", action="store_true", help="Synthetic data, no network")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument(
        "--report",
        choices=["json", "md", "both", "none"],
        default="json",
        help="Report format (default: json)",
    )
    parser.add_argument("--report-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--report-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--no-persist", action="store_true", help="Skip Postgres persist")
    args = parser.parse_args(argv)

    if not args.universe and not args.tickers and not args.tickers_file:
        parser.error("Specify --universe, --tickers, or --tickers-file")

    setup_logging("scan.log")
    use_cache = args.cache and not args.force_refresh
    report = None if args.report == "none" else args.report
    persist = not args.no_persist

    service = ScanService()
    service.run(
        universe_id=args.universe,
        tickers=args.tickers,
        tickers_file=args.tickers_file,
        use_cache=use_cache,
        dry_run=args.dry_run,
        output=args.output,
        report=report,
        report_json=args.report_json,
        report_md=args.report_md,
        persist=persist,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
