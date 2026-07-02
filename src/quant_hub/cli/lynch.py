"""quant-lynch — Peter Lynch fundamental stock screen with email."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from quant_hub.application.lynch_service import LynchScanService
from quant_hub.config import PRIMARY_INDEX_UNIVERSE
from quant_hub.logging_setup import setup_logging
from quant_hub.lynch.config import PRESET_LABELS, PRESETS

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Peter Lynch style stock screen (PEG, growth, balance sheet, categories)"
    )
    parser.add_argument(
        "--universe",
        default=PRIMARY_INDEX_UNIVERSE,
        help=f"Universe id (default: {PRIMARY_INDEX_UNIVERSE})",
    )
    parser.add_argument("--tickers", nargs="+", help="Explicit ticker list")
    parser.add_argument("--tickers-file", type=Path, help="Path to ticker file")
    parser.add_argument(
        "--preset",
        choices=PRESETS,
        default="summary",
        help="Screen preset (default: summary = all Lynch categories)",
    )
    parser.add_argument("--output", type=Path, default=None, help="CSV path (default: per-universe output)")
    parser.add_argument(
        "--report",
        choices=["json", "md", "both", "none"],
        default="both",
        help="Report export format",
    )
    parser.add_argument("--no-email", action="store_true", help="Skip email notification")
    parser.add_argument("--no-persist", action="store_true", help="Skip Postgres persist")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip persist and email (smoke test without side effects)",
    )
    args = parser.parse_args(argv)

    if not args.universe and not args.tickers and not args.tickers_file:
        parser.error("Specify --universe, --tickers, or --tickers-file")

    setup_logging("lynch.log")
    logger.info("Preset: %s", PRESET_LABELS.get(args.preset, args.preset))

    report = None if args.report == "none" else args.report
    dry_run = args.dry_run
    service = LynchScanService()
    result = service.run(
        universe_id=args.universe,
        tickers=args.tickers,
        tickers_file=args.tickers_file,
        preset=args.preset,
        output=args.output,
        report=report,
        persist=not args.no_persist and not dry_run,
        send_email=not args.no_email and not dry_run,
        job_name=None if dry_run else f"lynch-{args.preset}-{args.universe}",
    )
    return result.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
