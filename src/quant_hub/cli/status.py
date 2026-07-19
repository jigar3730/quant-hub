"""quant-hub — operational status CLI."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

from quant_hub.config import PRIMARY_INDEX_UNIVERSE
from quant_hub.history.ticker_projection import history_display_columns
from quant_hub.infrastructure.postgres.connection import apply_schema, ping
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository

STRATEGY_CHOICES = ("launchpad", "lynch")


def _cmd_status() -> int:
    repo = ScanRepository()
    job_repo = JobRunRepository()

    if not ping():
        print("Database: UNREACHABLE", file=sys.stderr)
        return 1

    print("Database: OK")
    counts = repo.table_counts()
    for table, count in counts.items():
        print(f"  {table}: {count}")

    for strategy in STRATEGY_CHOICES:
        runs = repo.list_runs(strategy_id=strategy, limit=5, exclude_fixtures=True)
        if not runs:
            continue
        print(f"\nRecent {strategy} scans:")
        for run in runs:
            print(
                f"  {run['scan_date']} {run['universe_id']} "
                f"actionable={run.get('actionable_count', 0)} "
                f"regime={run.get('regime_label', '?')}"
            )

    jobs = job_repo.recent_jobs(limit=5)
    if jobs:
        print("\nRecent jobs:")
        for job in jobs:
            print(
                f"  {job['job_name']} status={job['status']} "
                f"started={job['started_at']} "
                f"fetched={job.get('tickers_fetched', 0)}/"
                f"{job.get('tickers_requested', 0)}"
            )
    return 0


def _cmd_init_db(args: argparse.Namespace) -> int:
    apply_schema()
    if not args.quiet:
        print("Schema applied.")
    return 0


def _cmd_cleanup_fixtures() -> int:
    repo = ScanRepository()
    deleted = repo.delete_fixture_runs()
    print(f"Removed {deleted} fixture scan run(s).")
    return 0


def _cmd_cleanup_day(args: argparse.Namespace) -> int:
    if not ping():
        print("Database: UNREACHABLE", file=sys.stderr)
        return 1

    scan_date = args.date
    scan_repo = ScanRepository()
    job_repo = JobRunRepository()

    runs = scan_repo.preview_runs_for_scan_date(scan_date)
    if not runs and not args.include_jobs:
        print(f"No scan runs found for scan_date={scan_date}.")
        return 0

    print(f"scan_date={scan_date}")
    if runs:
        print(f"  scan_runs to delete: {len(runs)}")
        for row in runs:
            print(
                f"    {row['strategy_id']}/{row['universe_id']} "
                f"(size={row['universe_size']}, actionable={row['actionable_count']})"
            )
    if args.include_jobs:
        print(f"  job_runs: all with started_at on {scan_date} (America/New_York)")

    if args.dry_run:
        print("Dry run — no rows deleted.")
        return 0

    result = scan_repo.delete_runs_for_scan_date(scan_date)
    jobs_deleted = 0
    if args.include_jobs:
        jobs_deleted = job_repo.delete_jobs_for_market_date(scan_date)

    print(
        f"Removed {result['runs_deleted']} scan run(s), "
        f"{result['tickers_deleted']} ticker row(s)"
        + (f", {jobs_deleted} job run(s)" if args.include_jobs else "")
        + "."
    )
    return 0


def _cmd_report(universe_id: str, strategy_id: str) -> int:
    repo = ScanRepository()
    report = repo.load_report(strategy_id=strategy_id, universe_id=universe_id)
    if not report:
        print("No report found.", file=sys.stderr)
        return 1
    print(json.dumps(report["scan_summary"], indent=2))
    return 0


def _print_history_table(rows: list[dict]) -> None:
    if not rows:
        print("No actionable appearances found.")
        return
    columns = history_display_columns(rows)
    widths = {col: max(len(col), *(len(str(r.get(col, "") or "")) for r in rows)) for col in columns}
    header = "  ".join(col.ljust(widths[col]) for col in columns)
    print(header)
    print("-" * len(header))
    for row in rows:
        print("  ".join(str(row.get(col, "") or "").ljust(widths[col]) for col in columns))


def _cmd_ticker_history(args: argparse.Namespace) -> int:
    if not ping():
        print("Database: UNREACHABLE", file=sys.stderr)
        return 1

    repo = ScanRepository()
    limit = args.limit
    if limit == 0:
        total = repo.ticker_history_count(
            args.ticker,
            actionable_only=True,
            strategy_id=args.strategy,
            universe_id=args.universe,
            since=args.since,
            until=args.until,
            exclude_fixtures=True,
        )
        if total > 10_000:
            print(
                f"Warning: {total} rows match; fetching all may be slow.",
                file=sys.stderr,
            )
        limit = total or 1

    rows = repo.ticker_history(
        args.ticker,
        actionable_only=True,
        strategy_id=args.strategy,
        universe_id=args.universe,
        since=args.since,
        until=args.until,
        exclude_fixtures=True,
        limit=limit,
        offset=args.offset,
    )

    if args.json:
        print(json.dumps(rows, indent=2, default=str))
        return 0

    if args.csv:
        path = Path(args.csv)
        columns = history_display_columns(rows) if rows else []
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        print(f"Wrote {len(rows)} row(s) to {path}")
        return 0

    total = repo.ticker_history_count(
        args.ticker,
        actionable_only=True,
        strategy_id=args.strategy,
        universe_id=args.universe,
        since=args.since,
        until=args.until,
        exclude_fixtures=True,
    )
    print(f"{args.ticker.upper()}: {total} actionable appearance(s)")
    _print_history_table(rows)
    if args.offset + len(rows) < total:
        print(f"\n(showing offset {args.offset}, limit {limit}; use --offset to paginate)")
    return 0


def _cmd_ticker_show(args: argparse.Namespace) -> int:
    if not ping():
        print("Database: UNREACHABLE", file=sys.stderr)
        return 1

    repo = ScanRepository()
    report = repo.load_report(
        strategy_id=args.strategy,
        universe_id=args.universe,
        scan_date=args.date,
        exclude_fixtures=True,
    )
    if not report:
        print("No report found for that strategy/universe/date.", file=sys.stderr)
        return 1

    symbol = args.ticker.upper()
    ticker_data = next((t for t in report.get("tickers", []) if t.get("ticker") == symbol), None)
    if not ticker_data:
        print(f"{symbol} not found in scan {report.get('scan_date')}.", file=sys.stderr)
        return 1

    if args.json:
        payload = {
            "scan_date": str(report.get("scan_date")),
            "strategy_id": args.strategy,
            "universe_id": args.universe,
            "ticker": ticker_data,
        }
        print(json.dumps(payload, indent=2, default=str))
        return 0

    print(f"{symbol} — {args.strategy} — {args.universe} — {report.get('scan_date')}")
    print(json.dumps(ticker_data, indent=2, default=str))
    return 0


def _add_range_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--since", type=date.fromisoformat, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--until", type=date.fromisoformat, help="End date (YYYY-MM-DD)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-hub", description="Quant Hub operations")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Database and scan status")
    init_db = sub.add_parser("init-db", help="Apply Postgres schema")
    init_db.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success message (for cron/health checks)",
    )
    sub.add_parser(
        "cleanup-fixtures",
        help="Delete test fixture scan runs (test-upsert, custom, future dates)",
    )
    cleanup_day = sub.add_parser(
        "cleanup-day",
        help="Delete scan runs (and cascaded ticker results) for a scan_date",
    )
    cleanup_day.add_argument(
        "--date",
        type=date.fromisoformat,
        required=True,
        help="Scan date to purge (YYYY-MM-DD, matches scan_runs.scan_date)",
    )
    cleanup_day.add_argument(
        "--include-jobs",
        action="store_true",
        help="Also delete job_runs started on this calendar date (America/New_York)",
    )
    cleanup_day.add_argument("--dry-run", action="store_true", help="Preview only")

    report = sub.add_parser("report", help="Show latest scan summary")
    report.add_argument("--universe", default=PRIMARY_INDEX_UNIVERSE)
    report.add_argument("--strategy", default="launchpad", choices=STRATEGY_CHOICES)

    ticker = sub.add_parser("ticker", help="Ticker lookup across scan history")
    ticker_sub = ticker.add_subparsers(dest="ticker_command", required=True)

    history = ticker_sub.add_parser("history", help="Actionable appearances for a ticker")
    history.add_argument("ticker", help="Ticker symbol")
    history.add_argument("--strategy", choices=STRATEGY_CHOICES)
    history.add_argument("--universe")
    _add_range_args(history)
    history.add_argument("--limit", type=int, default=500, help="Max rows (0 = all)")
    history.add_argument("--offset", type=int, default=0)
    history.add_argument("--json", action="store_true", help="JSON output")
    history.add_argument("--csv", metavar="PATH", help="Write CSV to PATH")

    show = ticker_sub.add_parser("show", help="Full ticker snapshot from one scan")
    show.add_argument("ticker", help="Ticker symbol")
    show.add_argument("--strategy", required=True, choices=STRATEGY_CHOICES)
    show.add_argument("--universe", default=PRIMARY_INDEX_UNIVERSE)
    show.add_argument("--date", type=date.fromisoformat, help="Scan date (default: latest)")
    show.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "status":
        return _cmd_status()
    if args.command == "init-db":
        return _cmd_init_db(args)
    if args.command == "cleanup-fixtures":
        return _cmd_cleanup_fixtures()
    if args.command == "cleanup-day":
        return _cmd_cleanup_day(args)
    if args.command == "report":
        return _cmd_report(args.universe, args.strategy)
    if args.command == "ticker":
        if args.ticker_command == "history":
            return _cmd_ticker_history(args)
        if args.ticker_command == "show":
            return _cmd_ticker_show(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
