"""quant-hub — operational status CLI."""

from __future__ import annotations

import argparse
import json
import sys

from quant_hub.infrastructure.postgres.connection import apply_schema, ping
from quant_hub.infrastructure.postgres.repository import JobRunRepository, ScanRepository


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

    runs = repo.list_runs(limit=5)
    if runs:
        print("\nRecent scans:")
        for run in runs:
            print(
                f"  {run['scan_date']} {run['universe_id']} "
                f"actionable={run.get('actionable_count', 0)} "
                f"regime={run.get('regime_label', '?')}"
            )
    else:
        print("\nNo scan runs yet.")

    job = job_repo.latest_job()
    if job:
        print("\nLatest job:")
        print(
            f"  {job['job_name']} status={job['status']} "
            f"started={job['started_at']} "
            f"fetched={job.get('tickers_fetched', 0)}/"
            f"{job.get('tickers_requested', 0)}"
        )
    return 0


def _cmd_init_db() -> int:
    apply_schema()
    print("Schema applied.")
    return 0


def _cmd_report(universe_id: str, strategy_id: str) -> int:
    repo = ScanRepository()
    report = repo.load_report(strategy_id=strategy_id, universe_id=universe_id)
    if not report:
        print("No report found.", file=sys.stderr)
        return 1
    print(json.dumps(report["scan_summary"], indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-hub", description="Quant Hub operations")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Database and scan status")
    sub.add_parser("init-db", help="Apply Postgres schema")

    report = sub.add_parser("report", help="Show latest scan summary")
    report.add_argument("--universe", default="sp500")
    report.add_argument("--strategy", default="breakout")

    args = parser.parse_args(argv)

    if args.command == "status":
        return _cmd_status()
    if args.command == "init-db":
        return _cmd_init_db()
    if args.command == "report":
        return _cmd_report(args.universe, args.strategy)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
