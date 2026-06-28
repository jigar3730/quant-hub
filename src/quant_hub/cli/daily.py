"""quant-daily — scheduled daily scan with cache, persist, optional email."""

from __future__ import annotations

import argparse
import logging

from quant_hub.application.scan_service import ScanService
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def run_daily_scan(
    *,
    universe_id: str = "sp500",
    send_email: bool = True,
    use_cache: bool = True,
    job_name: str | None = "breakout-sp500-daily",
) -> int:
    setup_logging("scan.log")
    service = ScanService()
    result = service.run(
        universe_id=universe_id,
        use_cache=use_cache,
        report="both",
        send_email=send_email,
        job_name=job_name,
    )
    return result.exit_code()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily breakout scan")
    parser.add_argument("--universe", default="sp500", help="Universe id (default: sp500)")
    parser.add_argument("--no-email", action="store_true", help="Skip email")
    parser.add_argument("--no-cache", action="store_true", help="Disable parquet cache")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache")
    args = parser.parse_args(argv)

    use_cache = not args.no_cache and not args.force_refresh
    job_name = f"breakout-{args.universe}-daily"
    return run_daily_scan(
        universe_id=args.universe,
        send_email=not args.no_email,
        use_cache=use_cache,
        job_name=job_name,
    )


if __name__ == "__main__":
    raise SystemExit(main())
