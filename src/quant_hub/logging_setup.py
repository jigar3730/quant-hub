"""Shared CLI logging configuration."""

from __future__ import annotations

import logging
import sys

from quant_hub.config import LOG_DIR


def setup_logging(log_name: str = "scan.log") -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / log_name
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file),
        ],
        force=True,
    )
