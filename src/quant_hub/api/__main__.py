"""quant-api — run the read-only FastAPI service with uvicorn."""

from __future__ import annotations

import argparse

from quant_hub.logging_setup import setup_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Quant Hub read-only API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="Auto-reload on source changes")
    args = parser.parse_args()

    setup_logging()
    import uvicorn

    uvicorn.run(
        "quant_hub.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
