"""quant-mean-reversion — daily mean reversion rubric scan + trade plans."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from quant_hub.application.mean_reversion_service import MeanReversionScanService
from quant_hub.config import DEFAULT_MEAN_REVERSION_UNIVERSE
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Daily mean reversion scan (500 EMA / Bollinger / RSI rubric v2.2)"
    )
    parser.add_argument(
        "--universe",
        default=DEFAULT_MEAN_REVERSION_UNIVERSE,
        help=f"Universe id (default: {DEFAULT_MEAN_REVERSION_UNIVERSE})",
    )
    parser.add_argument("--tickers", nargs="+", help="Explicit ticker list")
    parser.add_argument("--tickers-file", type=str, help="Path to ticker file")
    parser.add_argument("--no-cache", action="store_true", help="Disable daily parquet cache")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache")
    parser.add_argument("--no-persist", action="store_true", help="Skip Postgres persist")
    parser.add_argument(
        "--output",
        default=None,
        help="High conviction CSV path (default: per-universe under data/output/mean_reversion/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip Postgres persist (smoke test)",
    )
    args = parser.parse_args(argv)

    setup_logging("mean_reversion.log")
    use_cache = not args.no_cache and not args.force_refresh

    if not args.universe and not args.tickers and not args.tickers_file:
        parser.error("Specify --universe, --tickers, or --tickers-file")

    service = MeanReversionScanService()
    dry_run = args.dry_run or args.no_persist
    result = service.run(
        universe_id=args.universe,
        tickers=args.tickers,
        tickers_file=Path(args.tickers_file) if args.tickers_file else None,
        use_cache=use_cache,
        force_refresh=args.force_refresh,
        output=Path(args.output) if args.output else None,
        persist=not dry_run,
        job_name=None if dry_run else f"mean-reversion-{args.universe}",
    )
    return result.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
