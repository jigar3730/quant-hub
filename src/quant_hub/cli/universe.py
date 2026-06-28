"""quant-universe — list and inspect configured universes."""

from __future__ import annotations

import argparse

from quant_hub.application.universe_service import UniverseService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Universe registry")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List configured universes")

    show = sub.add_parser("show", help="Show tickers for a universe")
    show.add_argument("universe_id")

    args = parser.parse_args(argv)
    service = UniverseService()

    if args.command == "list":
        for uid, name in sorted(service.list_universes().items()):
            print(f"{uid}\t{name}")
        return 0

    if args.command == "show":
        _, tickers = service.resolve(universe_id=args.universe_id)
        for t in tickers:
            print(t)
        print(f"# {len(tickers)} tickers", file=__import__("sys").stderr)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
