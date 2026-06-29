"""quant-backfill — historical point-in-time scans for ML training data."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from quant_hub.application.swing_backfill_service import SwingBackfillService
from quant_hub.infrastructure.postgres.connection import ping
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Historical backfill for ML training (point-in-time swing scans)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    swing = sub.add_parser("swing", help="Backfill weekly swing scans")
    swing.add_argument("--universe", default="sp500", help="Universe id (default: sp500)")
    swing.add_argument(
        "--since",
        type=date.fromisoformat,
        required=True,
        help="First Friday on or after this date (ISO)",
    )
    swing.add_argument(
        "--until",
        type=date.fromisoformat,
        default=None,
        help="Last Friday on or before this date (default: today)",
    )
    swing.add_argument(
        "--no-resume",
        action="store_true",
        help="Recompute and overwrite dates already in Postgres",
    )
    swing.add_argument("--dry-run", action="store_true", help="Compute only; no Postgres writes")
    swing.add_argument("--no-persist", action="store_true", help="Alias for dry-run without DB")

    args = parser.parse_args(argv)
    setup_logging("backfill.log")

    if not ping():
        print("Database unreachable", file=sys.stderr)
        return 1

    if args.command == "swing":
        dry_run = args.dry_run or args.no_persist
        service = SwingBackfillService()
        stats = service.run(
            universe_id=args.universe,
            since=args.since,
            until=args.until,
            resume=not args.no_resume,
            persist=not dry_run,
            dry_run=dry_run,
            job_name=None if dry_run else "swing-backfill",
        )
        print(stats.summary())
        if stats.errors:
            for err in stats.errors[:10]:
                print(f"  error: {err}", file=sys.stderr)
        return 0 if stats.dates_failed == 0 else 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
