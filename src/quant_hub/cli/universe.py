"""quant-universe — list, inspect, and refresh configured universes."""

from __future__ import annotations

import argparse
import sys

from quant_hub.application.universe_refresh import UniverseRefreshService
from quant_hub.application.universe_service import UniverseService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Universe registry")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List configured universes")

    show = sub.add_parser("show", help="Show tickers for a universe")
    show.add_argument("universe_id")

    refresh = sub.add_parser("refresh", help="Refresh a universe from its configured provider")
    refresh.add_argument("universe_id", help="Universe id (e.g. sp500_index)")
    refresh.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config without downloading or writing files",
    )

    args = parser.parse_args(argv)

    if args.command == "list":
        service = UniverseService()
        for uid, name in sorted(service.list_universes().items()):
            print(f"{uid}\t{name}")
        return 0

    if args.command == "show":
        service = UniverseService()
        _, tickers = service.resolve(universe_id=args.universe_id)
        for t in tickers:
            print(t)
        print(f"# {len(tickers)} tickers", file=sys.stderr)
        return 0

    if args.command == "refresh":
        service = UniverseRefreshService()
        result = service.refresh(args.universe_id, dry_run=args.dry_run)
        if args.dry_run:
            print(
                f"dry-run: would refresh {result.universe_id} "
                f"via {result.provider} -> {result.output_path}"
            )
        else:
            print(
                f"refreshed {result.universe_id}: {result.ticker_count} tickers "
                f"-> {result.output_path} ({result.refreshed_at})"
            )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
