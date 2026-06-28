"""quant-swing — weekly swing setup scan (finance-vibe logic, 10y/1wk OHLCV)."""

from __future__ import annotations

import argparse
import logging

from quant_hub.application.swing_service import SwingScanService
from quant_hub.config import DEFAULT_SWING_OUTPUT_CSV
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def run_swing_scan(
    *,
    universe_id: str = "sp500",
    send_email: bool = True,
    use_cache: bool = True,
    force_refresh: bool = False,
    job_name: str | None = "swing-weekly",
) -> int:
    setup_logging("swing.log")
    service = SwingScanService()
    service.run(
        universe_id=universe_id,
        use_cache=use_cache,
        force_refresh=force_refresh,
        send_email=send_email,
        job_name=job_name,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Weekly swing setup scan (10y / 1wk OHLCV, finance-vibe rules)"
    )
    parser.add_argument("--universe", default="sp500", help="Universe id (default: sp500)")
    parser.add_argument("--tickers", nargs="+", help="Explicit ticker list")
    parser.add_argument("--tickers-file", type=str, help="Path to ticker file")
    parser.add_argument("--no-email", action="store_true", help="Skip email")
    parser.add_argument("--no-cache", action="store_true", help="Disable weekly parquet cache")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache")
    parser.add_argument("--no-persist", action="store_true", help="Skip Postgres persist")
    parser.add_argument("--output", default=str(DEFAULT_SWING_OUTPUT_CSV))
    args = parser.parse_args(argv)

    setup_logging("swing.log")
    use_cache = not args.no_cache and not args.force_refresh

    if not args.universe and not args.tickers and not args.tickers_file:
        parser.error("Specify --universe, --tickers, or --tickers-file")

    from pathlib import Path

    service = SwingScanService()
    service.run(
        universe_id=args.universe,
        tickers=args.tickers,
        tickers_file=Path(args.tickers_file) if args.tickers_file else None,
        use_cache=use_cache,
        force_refresh=args.force_refresh,
        output=Path(args.output),
        persist=not args.no_persist,
        send_email=not args.no_email,
        job_name="swing-weekly-manual",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
