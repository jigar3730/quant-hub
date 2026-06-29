"""quant-ml — label pipeline and feature export (Phase 1 ML foundation)."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from quant_hub.application.ml_export_service import MLExportService
from quant_hub.application.ml_label_service import MLLabelService
from quant_hub.application.ml_cache_service import MLCacheService
from quant_hub.config import DEFAULT_LABEL_HORIZONS
from quant_hub.infrastructure.postgres.connection import ping
from quant_hub.infrastructure.postgres.outcomes_repository import OutcomesRepository
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def _parse_horizons(value: str) -> tuple[int, ...]:
    return tuple(int(h.strip()) for h in value.split(",") if h.strip())


def _cmd_label(args: argparse.Namespace) -> int:
    service = MLLabelService()
    stats = service.run(
        run_id=args.run_id,
        strategy_id=args.strategy,
        universe_id=args.universe,
        since=args.since,
        until=args.until,
        horizons=args.horizons,
        return_threshold_pct=args.threshold,
    )
    print(stats.summary())
    return 0 if stats.runs_processed > 0 or args.run_id else 1


def _cmd_export_features(args: argparse.Namespace) -> int:
    service = MLExportService()
    stats = service.run(
        run_id=args.run_id,
        strategy_id=args.strategy,
        universe_id=args.universe,
        since=args.since,
        until=args.until,
        horizon_days=args.horizon,
        include_labels=not args.no_labels,
        per_run_files=args.per_run,
    )
    print(stats.summary())
    return 0 if stats.rows_written > 0 else 1


def _cmd_status() -> int:
    repo = OutcomesRepository()
    total = repo.count_total()
    by_status = repo.count_by_status()
    print(f"signal_outcomes: {total}")
    for status, count in sorted(by_status.items()):
        print(f"  {status}: {count}")
    return 0


def _cmd_warm_cache(args: argparse.Namespace) -> int:
    service = MLCacheService()
    stats = service.warm_daily_prices(
        universe_id=args.universe,
        force_refresh=args.force_refresh,
    )
    print(stats.summary())
    return 0 if stats.tickers_requested > 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="ML foundation — forward-return labels and feature export"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    label = sub.add_parser("label", help="Compute forward-return labels for scan runs")
    label.add_argument("--run-id", type=int, help="Label a single scan run by id")
    label.add_argument("--strategy", choices=("breakout", "swing", "lynch"))
    label.add_argument("--universe", help="Universe id filter (e.g. sp500)")
    label.add_argument("--since", type=date.fromisoformat)
    label.add_argument("--until", type=date.fromisoformat)
    label.add_argument(
        "--horizons",
        type=_parse_horizons,
        default=DEFAULT_LABEL_HORIZONS,
        help=f"Comma-separated horizons (default: {','.join(map(str, DEFAULT_LABEL_HORIZONS))})",
    )
    label.add_argument(
        "--threshold",
        type=float,
        default=2.0,
        help="Binary label threshold: forward return >= threshold pct",
    )

    export = sub.add_parser("export-features", help="Export flattened features to Parquet")
    export.add_argument("--run-id", type=int)
    export.add_argument("--strategy", choices=("breakout", "swing", "lynch"))
    export.add_argument("--universe")
    export.add_argument("--since", type=date.fromisoformat)
    export.add_argument("--until", type=date.fromisoformat)
    export.add_argument(
        "--horizon",
        type=int,
        help="Label horizon to join (default: 10 when labels included)",
    )
    export.add_argument("--no-labels", action="store_true", help="Export features only")
    export.add_argument(
        "--per-run",
        action="store_true",
        help="Write one Parquet file per scan run instead of a combined export",
    )

    sub.add_parser("status", help="Show signal_outcomes counts")

    warm = sub.add_parser("warm-cache", help="Download extended daily OHLCV for labeling")
    warm.add_argument("--universe", default="sp500", help="Universe id (default: sp500)")
    warm.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass parquet cache and re-fetch from yfinance",
    )

    args = parser.parse_args(argv)
    setup_logging("ml.log")

    if not ping():
        print("Database unreachable", file=sys.stderr)
        return 1

    if args.command == "label":
        return _cmd_label(args)
    if args.command == "export-features":
        return _cmd_export_features(args)
    if args.command == "status":
        return _cmd_status()
    if args.command == "warm-cache":
        return _cmd_warm_cache(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
