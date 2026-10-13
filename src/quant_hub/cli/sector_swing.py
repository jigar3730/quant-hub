"""quant-sector-swing — scheduled sector-ETF swing scan (premarket, prior-session close)."""

from __future__ import annotations

import argparse
import logging

from quant_hub.application.sector_swing_service import SectorSwingScanService
from quant_hub.logging_setup import setup_logging
from quant_hub.sector_swing import config as C
from quant_hub.sector_swing.runner import SectorSwingError

logger = logging.getLogger(__name__)


def run_sector_swing(
    *,
    universe_id: str = C.UNIVERSE_ID,
    use_cache: bool = True,
    dry_run: bool = False,
    allow_stale: bool = False,
    equity: float | None = None,
    risk_pct: float | None = None,
    report: str = "both",
) -> int:
    setup_logging("scan.log")
    service = SectorSwingScanService()
    try:
        result = service.run(
            universe_id=universe_id,
            use_cache=use_cache,
            dry_run=dry_run,
            allow_stale=allow_stale,
            equity=equity,
            risk_pct=risk_pct,
            report=report,
            persist=not dry_run,
        )
    except SectorSwingError as exc:
        logger.error("Sector swing scan FAILED (nothing persisted): %s", exc)
        return 1
    return result.exit_code()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sector-ETF swing scan (research tool only)")
    parser.add_argument("--universe", default=C.UNIVERSE_ID, help="Universe id")
    parser.add_argument("--dry-run", action="store_true", help="Synthetic data; no persist/job row")
    parser.add_argument("--no-cache", action="store_true", help="Disable parquet cache")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache")
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help="Proceed when SPY's last bar is older than the expected session (recorded in report)",
    )
    parser.add_argument(
        "--equity",
        type=float,
        help=f"Assumed account equity (default: ${C.EQUITY_ENV} or {C.DEFAULT_EQUITY:,.0f})",
    )
    parser.add_argument(
        "--risk-pct",
        type=float,
        help=f"Fraction of equity risked per trade (default {C.DEFAULT_PARAMS.risk_pct})",
    )
    parser.add_argument("--report", choices=["json", "md", "both"], default="both")
    args = parser.parse_args(argv)

    if args.equity is not None and args.equity <= 0:
        parser.error("--equity must be positive")
    if args.risk_pct is not None and not 0 < args.risk_pct < 1:
        parser.error("--risk-pct must be a fraction between 0 and 1 (e.g. 0.01)")

    return run_sector_swing(
        universe_id=args.universe,
        use_cache=not (args.no_cache or args.force_refresh),
        dry_run=args.dry_run,
        allow_stale=args.allow_stale,
        equity=args.equity,
        risk_pct=args.risk_pct,
        report=args.report,
    )


if __name__ == "__main__":
    raise SystemExit(main())
