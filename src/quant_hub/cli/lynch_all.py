"""quant-lynch-all — run Lynch scan across stock universes."""

from __future__ import annotations

import argparse
import logging

from quant_hub.application.lynch_service import LynchScanService
from quant_hub.lynch.config import PRESETS, PRESET_LABELS
from quant_hub.logging_setup import setup_logging
from quant_hub.universes.batch import list_universe_ids

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Lynch scan on all stock universes (skips lynch_enabled: false)"
    )
    parser.add_argument(
        "--preset",
        choices=PRESETS,
        default="summary",
        help="Screen preset (default: summary)",
    )
    parser.add_argument("--no-email", action="store_true", help="Skip email after each universe")
    parser.add_argument(
        "--report",
        choices=["json", "md", "both", "none"],
        default="both",
        help="Report export format",
    )
    parser.add_argument(
        "--universes",
        nargs="+",
        help="Subset of universe ids (default: all Lynch-enabled universes)",
    )
    args = parser.parse_args(argv)

    setup_logging("lynch.log")
    logger.info("Preset: %s", PRESET_LABELS.get(args.preset, args.preset))
    report = None if args.report == "none" else args.report
    universe_ids = list_universe_ids(strategy="lynch", explicit=args.universes)

    service = LynchScanService()
    failed: list[str] = []
    for uid in universe_ids:
        logger.info("=== Lynch universe: %s ===", uid)
        try:
            result = service.run(
                universe_id=uid,
                preset=args.preset,
                report=report,
                send_email=not args.no_email,
                job_name=f"lynch-{args.preset}-{uid}-batch",
            )
            if result.exit_code() != 0:
                failed.append(uid)
        except Exception:
            logger.exception("Lynch scan failed for universe %s", uid)
            failed.append(uid)

    if failed:
        logger.error("Failed Lynch universes: %s", ", ".join(failed))
        return 1

    logger.info("Completed Lynch scans for %d universes", len(universe_ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
