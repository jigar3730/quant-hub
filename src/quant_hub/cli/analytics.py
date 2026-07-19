"""quant-analytics — build digest analytics payloads (no email)."""

from __future__ import annotations

import argparse
import logging
from datetime import date

from quant_hub.application.digest_service import DigestService
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build Quant Hub analytics payloads for digests")
    sub = parser.add_subparsers(dest="command", required=True)

    weekly = sub.add_parser("weekly", help="Build weekly Lynch analytics JSON with Launchpad overlap")
    weekly.add_argument("--date", type=date.fromisoformat, help="Lynch date (default: today)")

    args = parser.parse_args(argv)
    setup_logging("digest.log")

    service = DigestService()
    if args.command == "weekly":
        payload = service.run_analytics_weekly(lynch_date=args.date)
        logger.info(
            "Weekly analytics: %d Launchpad overlaps, %d Lynch top",
            len(payload.get("launchpad_overlap") or []),
            len(payload.get("lynch_top") or []),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
