"""quant-launchpad-daily — scheduled daily Launchpad scan."""

from __future__ import annotations

import argparse
import logging

from quant_hub.application.scan_service import ScanService
from quant_hub.application.universe_service import UniverseService
from quant_hub.config import PRIMARY_INDEX_UNIVERSE
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def run_daily_scan(
    *,
    universe_id: str = PRIMARY_INDEX_UNIVERSE,
    send_email: bool = True,
    use_cache: bool = True,
    dry_run: bool = False,
    job_name: str | None = None,
) -> int:
    setup_logging("scan.log")
    if UniverseService().registry.get_eligibility_mode(universe_id) == "etf":
        logger.warning(
            "Skipping launchpad scan for ETF-mode universe %s "
            "(Launchpad rubric is single-stock only)",
            universe_id,
        )
        return 0
    service = ScanService(strategy_id="launchpad")
    result = service.run(
        universe_id=universe_id,
        use_cache=use_cache,
        dry_run=dry_run,
        report="both",
        send_email=send_email and not dry_run,
        persist=not dry_run,
        job_name=None if dry_run else job_name,
    )
    return result.exit_code()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily Launchpad Reversal scan")
    parser.add_argument(
        "--universe",
        default=PRIMARY_INDEX_UNIVERSE,
        help=f"Universe id (default: {PRIMARY_INDEX_UNIVERSE})",
    )
    parser.add_argument("--no-email", action="store_true", help="Skip email")
    parser.add_argument("--no-cache", action="store_true", help="Disable parquet cache")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache")
    parser.add_argument("--dry-run", action="store_true", help="Synthetic data; skip persist")
    args = parser.parse_args(argv)

    use_cache = not args.no_cache and not args.force_refresh
    job_name = f"launchpad-{args.universe}-daily"
    return run_daily_scan(
        universe_id=args.universe,
        send_email=not args.no_email,
        use_cache=use_cache,
        dry_run=args.dry_run,
        job_name=job_name,
    )


if __name__ == "__main__":
    raise SystemExit(main())
