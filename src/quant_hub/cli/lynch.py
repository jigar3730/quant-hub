"""quant-lynch — Peter Lynch fundamental stock screen with email."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from quant_hub.application.lynch_service import LynchScanService
from quant_hub.lynch.config import PRESETS, PRESET_LABELS
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Peter Lynch style stock screen (PEG, growth, balance sheet, categories)"
    )
    parser.add_argument("--universe", default="sp500", help="Universe id (default: sp500)")
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
    args = parser.parse_args(argv)

    if not args.universe and not args.tickers and not args.tickers_file:
        parser.error("Specify --universe, --tickers, or --tickers-file")

    setup_logging("lynch.log")
    logger.info("Preset: %s", PRESET_LABELS.get(args.preset, args.preset))

    report = None if args.report == "none" else args.report
    service = LynchScanService()
    service.run(
        universe_id=args.universe,
        tickers=args.tickers,
        tickers_file=args.tickers_file,
        preset=args.preset,
        output=args.output,
        report=report,
        persist=not args.no_persist,
        send_email=not args.no_email,
        job_name=f"lynch-{args.preset}-{args.universe}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
