"""quant-scan-all — run breakout scan across all configured universes."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from quant_hub.application.scan_service import ScanService
from quant_hub.config import UNIVERSES_CONFIG
from quant_hub.logging_setup import setup_logging

logger = logging.getLogger(__name__)


def _all_universe_ids(config_path: Path) -> list[str]:
    data = json.loads(config_path.read_text())
    return list(data.get("universes", {}).keys())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run breakout scan on all configured universes")
    parser.add_argument("--cache", action="store_true", help="Use parquet price cache")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass cache")
    parser.add_argument("--email", action="store_true", help="Send email after each universe scan")
    parser.add_argument(
        "--universes",
        nargs="+",
        help="Subset of universe ids (default: all configured universes)",
    )
    parser.add_argument("--report", choices=["json", "md", "both", "none"], default="none")
    args = parser.parse_args(argv)

    setup_logging("scan.log")
    use_cache = args.cache and not args.force_refresh
    universe_ids = args.universes or _all_universe_ids(UNIVERSES_CONFIG)

    service = ScanService()
    failed: list[str] = []
    for uid in universe_ids:
        logger.info("=== Scanning universe: %s ===", uid)
        try:
            service.run(
                universe_id=uid,
                use_cache=use_cache,
                report=None if args.report == "none" else args.report,
                send_email=args.email,
                job_name=f"breakout-{uid}-batch",
            )
        except Exception:
            logger.exception("Scan failed for universe %s", uid)
            failed.append(uid)

    if failed:
        logger.error("Failed universes: %s", ", ".join(failed))
        return 1

    logger.info("Completed scans for %d universes", len(universe_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
