"""quant-backfill — historical point-in-time Launchpad scans for ML training data."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from quant_hub.application.launchpad_backfill_service import LaunchpadBackfillService
from quant_hub.config import PRIMARY_INDEX_UNIVERSE
from quant_hub.infrastructure.postgres.connection import ping
from quant_hub.logging_setup import setup_logging
from quant_hub.ml.backfill_dates import earliest_daily_backfill_supported
from quant_hub.universes.batch import list_universe_ids

logger = logging.getLogger(__name__)


def _add_range_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--universe",
        default=PRIMARY_INDEX_UNIVERSE,
        help=f"Universe id (default: {PRIMARY_INDEX_UNIVERSE})",
    )
    parser.add_argument(
        "--since",
        type=date.fromisoformat,
        required=True,
        help="First Saturday on or after this date (ISO)",
    )
    parser.add_argument(
        "--until",
        type=date.fromisoformat,
        default=None,
        help="Last Saturday on or before this date (default: today)",
    )


def _cmd_launchpad_coverage(args: argparse.Namespace) -> int:
    service = LaunchpadBackfillService()
    universe_ids = (
        list_universe_ids(strategy_id="launchpad") if args.all_universes else [args.universe]
    )
    any_missing = False
    for universe_id in universe_ids:
        report = service.coverage(
            universe_id=universe_id,
            since=args.since,
            until=args.until,
        )
        print(f"launchpad/{universe_id} {report.summary()}")
        for line in report.detail_lines(missing_preview=args.preview):
            print(f"  {line}")
        if report.missing_dates:
            any_missing = True
    supported = earliest_daily_backfill_supported()
    print(f"  earliest_supported≈{supported} (5y daily cache, 200-bar minimum)")
    if any_missing:
        target = "--all-universes" if args.all_universes else f"--universe {args.universe}"
        print(
            f"\nRun backfill:\n"
            f"  quant-backfill launchpad {target} "
            f"--since {args.since}" + (f" --until {args.until}" if args.until else "")
        )
        return 1
    return 0


def _cmd_launchpad(args: argparse.Namespace) -> int:
    dry_run = args.dry_run or args.no_persist
    service = LaunchpadBackfillService()
    universe_ids = (
        list_universe_ids(strategy_id="launchpad") if args.all_universes else [args.universe]
    )
    failed = 0
    for universe_id in universe_ids:
        if not dry_run:
            report = service.coverage(
                universe_id=universe_id,
                since=args.since,
                until=args.until,
            )
            print(f"pre-flight launchpad/{universe_id}: {report.summary()}")
            if report.missing_dates:
                preview = ", ".join(str(d) for d in report.missing_dates[:3])
                extra = (
                    f" ... +{len(report.missing_dates) - 3}"
                    if len(report.missing_dates) > 3
                    else ""
                )
                print(
                    f"  will write {len(report.missing_dates)} Saturdays "
                    f"starting [{preview}{extra}]"
                )
            else:
                print(
                    "  nothing to write (all dates already in Postgres; "
                    "use --no-resume to overwrite)"
                )

        stats = service.run(
            universe_id=universe_id,
            since=args.since,
            until=args.until,
            resume=not args.no_resume,
            persist=not dry_run,
            dry_run=dry_run,
            job_name=None if dry_run else f"launchpad-backfill-{universe_id}",
        )
        print(f"launchpad/{universe_id}: {stats.summary()}")
        if stats.errors:
            for err in stats.errors[:10]:
                print(f"  error: {err}", file=sys.stderr)
            if len(stats.errors) > 10:
                print(f"  ... +{len(stats.errors) - 10} more errors", file=sys.stderr)
        if stats.dates_failed:
            failed += 1
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Historical Launchpad backfill for ML training (point-in-time daily OHLCV)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    launchpad = sub.add_parser(
        "launchpad",
        help="Backfill Saturday launchpad scans (point-in-time daily OHLCV)",
    )
    _add_range_args(launchpad)
    launchpad.add_argument(
        "--all-universes",
        action="store_true",
        help="Backfill every stock universe used by quant-launchpad-all",
    )
    launchpad.add_argument(
        "--no-resume",
        action="store_true",
        help="Recompute and overwrite dates already in Postgres",
    )
    launchpad.add_argument("--dry-run", action="store_true", help="Compute only; no Postgres writes")
    launchpad.add_argument("--no-persist", action="store_true", help="Alias for dry-run without DB")

    coverage = sub.add_parser(
        "coverage",
        help="Show planned vs existing Launchpad scan dates (no scans run)",
    )
    _add_range_args(coverage)
    coverage.add_argument(
        "--preview",
        type=int,
        default=5,
        help="How many missing dates to list (default: 5)",
    )
    coverage.add_argument(
        "--all-universes",
        action="store_true",
        help="Report coverage for every stock universe",
    )

    args = parser.parse_args(argv)
    setup_logging("backfill.log")

    if not ping():
        print("Database unreachable", file=sys.stderr)
        return 1

    if args.command == "coverage":
        return _cmd_launchpad_coverage(args)
    if args.command == "launchpad":
        return _cmd_launchpad(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
