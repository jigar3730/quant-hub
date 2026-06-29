"""quant-swing-all — run swing scan across configured universes."""

from __future__ import annotations

import argparse
import logging

from quant_hub.application.swing_service import SwingScanService
from quant_hub.logging_setup import setup_logging
from quant_hub.universes.batch import list_universe_ids

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run swing scan on all configured universes")
    parser.add_argument("--no-email", action="store_true", help="Skip email after each universe")
    parser.add_argument("--no-cache", action="store_true", help="Disable weekly parquet cache")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache")
    parser.add_argument(
        "--universes",
        nargs="+",
        help="Subset of universe ids (default: all configured universes)",
    )
    args = parser.parse_args(argv)

    setup_logging("swing.log")
    use_cache = not args.no_cache and not args.force_refresh
    universe_ids = list_universe_ids(explicit=args.universes)

    service = SwingScanService()
    failed: list[str] = []
    for uid in universe_ids:
        logger.info("=== Swing universe: %s ===", uid)
        try:
            result = service.run(
                universe_id=uid,
                use_cache=use_cache,
                force_refresh=args.force_refresh,
                send_email=not args.no_email,
                job_name=f"swing-{uid}-batch",
            )
            if result.exit_code() != 0:
                failed.append(uid)
        except Exception:
            logger.exception("Swing scan failed for universe %s", uid)
            failed.append(uid)

    if failed:
        logger.error("Failed swing universes: %s", ", ".join(failed))
        return 1

    logger.info("Completed swing scans for %d universes", len(universe_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
