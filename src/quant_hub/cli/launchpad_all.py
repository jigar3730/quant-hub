"""quant-launchpad-all — run Launchpad scan across all configured universes."""

from __future__ import annotations

import argparse
import logging

from quant_hub.application.scan_service import ScanService
from quant_hub.logging_setup import setup_logging
from quant_hub.universes.batch import list_universe_ids

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Launchpad scan on all configured universes"
    )
    parser.add_argument("--cache", action="store_true", help="Use parquet price cache")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache")
    parser.add_argument("--email", action="store_true", help="Send email after each universe scan")
    parser.add_argument("--universes", nargs="+", help="Subset of universe ids")
    parser.add_argument("--report", choices=["json", "md", "both", "none"], default="none")
    args = parser.parse_args(argv)

    setup_logging("scan.log")
    use_cache = args.cache and not args.force_refresh
    universe_ids = list_universe_ids(strategy="launchpad", explicit=args.universes)

    service = ScanService(strategy_id="launchpad")
    failed: list[str] = []
    email_failed: list[str] = []
    for uid in universe_ids:
        logger.info("=== Launchpad scanning universe: %s ===", uid)
        try:
            result = service.run(
                universe_id=uid,
                use_cache=use_cache,
                report=None if args.report == "none" else args.report,
                send_email=args.email,
                job_name=f"launchpad-{uid}-batch",
            )
            if args.email and not result.ok:
                email_failed.append(uid)
        except Exception:
            logger.exception("Launchpad scan failed for universe %s", uid)
            failed.append(uid)

    if failed:
        logger.error("Failed universes: %s", ", ".join(failed))
        return 1
    if email_failed:
        logger.error("Email not sent for universes: %s", ", ".join(email_failed))
        return 1

    logger.info("Completed launchpad scans for %d universes", len(universe_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
