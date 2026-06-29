"""quant-digest — consolidated daily and weekly email digests."""

from __future__ import annotations

import argparse
import logging
from datetime import date

from quant_hub.application.digest_service import DigestService
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send consolidated Quant Hub digest emails")
    sub = parser.add_subparsers(dest="command", required=True)

    daily = sub.add_parser("daily", help="Daily breakout quality digest (Mon–Fri)")
    daily.add_argument("--date", type=date.fromisoformat, help="Scan date (default: today)")
    daily.add_argument("--no-email", action="store_true", help="Build only, do not send")
    daily.add_argument("--force", action="store_true", help="Send even if already sent today")

    weekly = sub.add_parser("weekly", help="Weekly cross-strategy digest (Sat)")
    weekly.add_argument("--date", type=date.fromisoformat, help="Lynch scan date (default: today)")
    weekly.add_argument("--no-email", action="store_true", help="Build only, do not send")
    weekly.add_argument("--force", action="store_true", help="Send even if already sent this week")
    weekly.add_argument(
        "--rebuild-analytics",
        action="store_true",
        help="Ignore cached weekly payload and rebuild from Postgres",
    )

    args = parser.parse_args(argv)
    setup_logging("digest.log")
    service = DigestService()

    if args.command == "daily":
        result = service.run_daily(
            scan_date=args.date,
            send_email=not args.no_email,
            force=args.force,
        )
    else:
        result = service.run_weekly(
            lynch_date=args.date,
            send_email=not args.no_email,
            force=args.force,
            use_cached_payload=not args.rebuild_analytics,
        )

    return result.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
