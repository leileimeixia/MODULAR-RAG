"""Minimal MCP stdio server entrypoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

if __package__ in (None, ""):
    src_root = Path(__file__).resolve().parents[1]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

from mcp_server.protocol_handler import ProtocolHandler, parse_error_response
from mcp_server.tools import default_tools


def main(
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run a line-delimited JSON-RPC stdio loop."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    handler = ProtocolHandler(tools=default_tools())
    _log(stderr, "MCP stdio server starting")

    for line in stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = parse_error_response()
        else:
            response = handler.handle_message(request)
        if response is not None:
            _write_message(stdout, response)

    _log(stderr, "MCP stdio server stopped")
    return 0

def _write_message(stdout: TextIO, payload: dict[str, Any]) -> None:
    stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    stdout.flush()


def _log(stderr: TextIO, message: str) -> None:
    print(message, file=stderr)


if __name__ == "__main__":
    raise SystemExit(main())
