"""quant-sector-swing-positions — log paper fills and review sector-swing positions.

Research tool only: this records fills you make yourself; it never places orders. The daily
``quant-sector-swing`` scan refreshes stops and exit signals; ``refresh`` does the same on demand.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from typing import Any

from quant_hub.application.sector_swing_positions_service import (
    SectorSwingPositionsService,
    realized_r,
    suggested_action,
)
from quant_hub.infrastructure.postgres.sector_swing_positions_repository import PositionError
from quant_hub.logging_setup import setup_logging
from quant_hub.sector_swing.positions import TRAIL_MODES

logger = logging.getLogger(__name__)


def _fmt(value: Any, spec: str = ".2f") -> str:
    return "-" if value is None else format(value, spec)


def _print_positions(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No positions.")
        return
    header = (
        f"{'id':>4}  {'ticker':<6} {'status':<6} {'entry':>10} {'@':>8} {'shares':>9} "
        f"{'stop':>8} {'target':>8} {'last':>8} {'bars':>4}  {'realized':>9} {'R':>5}  signal"
    )
    print(header)
    print("-" * len(header))
    for p in rows:
        r = realized_r(p)
        print(
            f"{p['id']:>4}  {p['ticker']:<6} {p['status']:<6} {str(p['entry_date']):>10} "
            f"{p['entry_price']:>8.2f} {p['open_shares']:>4}/{p['initial_shares']:<4} "
            f"{p['current_stop']:>8.2f} {p['target_price']:>8.2f} {_fmt(p['last_close']):>8} "
            f"{p['bars_held']:>4}  {p['realized_pnl']:>9,.2f} {_fmt(r, '.2f'):>5}  "
            f"{p['exit_signal'] or ''}"
        )
    for p in rows:
        action = suggested_action(p)
        if action and p["status"] == "open":
            print(f"\n  >> {p['ticker']} (id {p['id']}): {action} "
                  f"[{p['exit_signal_date']}: {p['exit_signal_detail']}]")


def _cmd_open(service: SectorSwingPositionsService, args: argparse.Namespace) -> int:
    result = service.open_position(
        args.ticker,
        price=args.price,
        shares=args.shares,
        entry_date=args.date,
        stop=args.stop,
        trail_mode=args.trail,
        notes=args.notes,
    )
    p = result.position
    print(
        f"Opened position {p['id']}: {p['ticker']} {p['initial_shares']} sh @ "
        f"{p['entry_price']:.2f} on {p['entry_date']}; stop {p['initial_stop']:.2f}, "
        f"2R target {p['target_price']:.2f}, trail {p['trail_mode']}"
    )
    for message in result.warnings:
        print(f"  warning: {message}")
    return 0


def _cmd_sell(service: SectorSwingPositionsService, args: argparse.Namespace) -> int:
    p = service.sell(
        args.position,
        price=args.price,
        shares=None if args.all else args.shares,
        fill_date=args.date,
        reason=args.reason,
    )
    state = "closed" if p["status"] == "closed" else f"{p['open_shares']} sh still open"
    r = realized_r(p)
    print(f"Recorded sell for {p['ticker']} (id {p['id']}): {state}; realized "
          f"${p['realized_pnl']:,.2f} ({_fmt(r)} R)")
    return 0


def _cmd_list(service: SectorSwingPositionsService, args: argparse.Namespace) -> int:
    status = None if args.all else "open"
    _print_positions(service.repo.list_positions(status=status, limit=args.limit))
    return 0


def _cmd_show(service: SectorSwingPositionsService, args: argparse.Namespace) -> int:
    p = service.resolve(args.position)
    _print_positions([p])
    print(f"\n  trail {p['trail_mode']} (level {_fmt(p['trail_level'])}), "
          f"highest close {_fmt(p['highest_close'])}, target reached: {p['target_reached']}, "
          f"max hold {p['max_hold_days']} bars, last bar {p['last_bar_date'] or '-'}")
    if p.get("notes"):
        print(f"  notes: {p['notes']}")
    print("\n  fills:")
    for f in service.repo.list_fills(p["id"]):
        print(f"    {f['fill_date']}  {f['side']:<4} {f['shares']:>5} @ {f['price']:.2f}"
              f"  {f['reason'] or ''}")
    return 0


def _cmd_refresh(service: SectorSwingPositionsService, args: argparse.Namespace) -> int:
    result = service.refresh(use_cache=not args.force_refresh)
    if not result.updated and not result.failed:
        print("No open positions.")
        return 0
    print(f"Prices as of {result.as_of} (expected session {result.expected_session})")
    if result.stale:
        print("  warning: price data is older than the expected session; signals may lag")
    for row, error in result.failed:
        print(f"  FAILED {row['ticker']} (id {row['id']}): {error}")
    _print_positions(service.repo.list_positions(status="open"))
    return 1 if result.failed else 0


def _cmd_delete(service: SectorSwingPositionsService, args: argparse.Namespace) -> int:
    p = service.resolve(args.position)
    if not args.yes:
        print(f"Would delete position {p['id']} ({p['ticker']}) and all its fills. "
              "Re-run with --yes to confirm.")
        return 1
    service.repo.delete_position(p["id"])
    print(f"Deleted position {p['id']} ({p['ticker']}).")
    return 0


def _date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sector-ETF swing paper positions (research tool only; no broker)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_open = sub.add_parser("open", help="Log an entry fill")
    p_open.add_argument("ticker")
    p_open.add_argument("--price", type=float, required=True, help="Actual fill price")
    p_open.add_argument("--shares", type=int, required=True)
    p_open.add_argument("--date", type=_date, help="Fill date (default today)")
    p_open.add_argument("--stop", type=float, help="Initial stop (default: latest scan's plan)")
    p_open.add_argument("--trail", choices=TRAIL_MODES, help="Trailing exit after the 2R target")
    p_open.add_argument("--notes")
    p_open.set_defaults(func=_cmd_open)

    p_sell = sub.add_parser("sell", help="Log an exit fill (partial or full)")
    p_sell.add_argument("position", help="Position id or ticker")
    p_sell.add_argument("--price", type=float, required=True)
    qty = p_sell.add_mutually_exclusive_group(required=True)
    qty.add_argument("--shares", type=int)
    qty.add_argument("--all", action="store_true", help="Sell every open share")
    p_sell.add_argument("--date", type=_date, help="Fill date (default today)")
    p_sell.add_argument("--reason", help="Default: the current exit signal, else 'manual'")
    p_sell.set_defaults(func=_cmd_sell)

    p_list = sub.add_parser("list", help="Open positions (or --all)")
    p_list.add_argument("--all", action="store_true", help="Include closed positions")
    p_list.add_argument("--limit", type=int, default=50)
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="One position with its fills")
    p_show.add_argument("position", help="Position id or ticker")
    p_show.set_defaults(func=_cmd_show)

    p_refresh = sub.add_parser("refresh", help="Recompute stops and exit signals now")
    p_refresh.add_argument("--force-refresh", action="store_true", help="Bypass the price cache")
    p_refresh.set_defaults(func=_cmd_refresh)

    p_delete = sub.add_parser("delete", help="Remove a position logged by mistake")
    p_delete.add_argument("position", help="Position id or ticker")
    p_delete.add_argument("--yes", action="store_true")
    p_delete.set_defaults(func=_cmd_delete)
    return parser


def main(argv: list[str] | None = None, service: SectorSwingPositionsService | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging("scan.log")
    service = service or SectorSwingPositionsService()
    try:
        return args.func(service, args)
    except PositionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
