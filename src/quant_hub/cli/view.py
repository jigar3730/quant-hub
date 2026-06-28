"""Launch the Streamlit dashboard."""

import subprocess
import sys
from pathlib import Path

DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"


def main(argv: list[str] | None = None) -> int:
    extra = list(argv) if argv is not None else sys.argv[1:]
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(DASHBOARD),
        "--server.headless",
        "true",
        *extra,
    ]
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
