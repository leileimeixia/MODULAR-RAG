"""Launch the local Streamlit dashboard."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Run the Streamlit dashboard app and return its process exit code."""
    project_root = Path(__file__).resolve().parents[1]
    app_path = project_root / "src" / "observability" / "dashboard" / "app.py"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        *(argv or []),
    ]
    return subprocess.call(command, cwd=project_root)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
