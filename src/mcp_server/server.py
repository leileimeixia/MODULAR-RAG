"""Minimal MCP stdio server entrypoint."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO


SERVER_NAME = "modular-rag-mcp-server"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOL_VERSION = "2024-11-05"


def main(
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run a line-delimited JSON-RPC stdio loop."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    _log(stderr, "MCP stdio server starting")

    for line in stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = _handle_request(request)
        except Exception as exc:  # noqa: BLE001 - protocol boundary converts all errors.
            response = _error_response(None, -32603, f"Internal error: {exc}")
        if response is not None:
            _write_message(stdout, response)

    _log(stderr, "MCP stdio server stopped")
    return 0


def _handle_request(request: Any) -> dict[str, Any] | None:
    if not isinstance(request, dict):
        return _error_response(None, -32600, "Invalid Request")
    request_id = request.get("id")
    if request.get("jsonrpc") != "2.0" or "method" not in request:
        return _error_response(request_id, -32600, "Invalid Request")

    method = request["method"]
    params = request.get("params", {})
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": _initialize_result(params),
        }
    if method == "notifications/initialized":
        return None
    return _error_response(request_id, -32601, f"Method not found: {method}")


def _initialize_result(params: Any) -> dict[str, Any]:
    client_protocol = ""
    if isinstance(params, dict):
        client_protocol = str(params.get("protocolVersion", ""))
    return {
        "protocolVersion": client_protocol or SUPPORTED_PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
        },
    }


def _error_response(
    request_id: Any,
    code: int,
    message: str,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _write_message(stdout: TextIO, payload: dict[str, Any]) -> None:
    stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    stdout.flush()


def _log(stderr: TextIO, message: str) -> None:
    print(message, file=stderr)


if __name__ == "__main__":
    raise SystemExit(main())
