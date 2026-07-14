"""Integration tests for the MCP stdio server entrypoint."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = PROJECT_ROOT / "src" / "mcp_server" / "server.py"


def _run_server(requests: list[dict]) -> subprocess.CompletedProcess[str]:
    payload = "".join(json.dumps(request) + "\n" for request in requests)
    return subprocess.run(
        [sys.executable, str(SERVER_PATH)],
        input=payload,
        text=True,
        capture_output=True,
        timeout=5,
        cwd=PROJECT_ROOT,
        check=False,
    )


def test_mcp_server_initialize_uses_stdout_only_for_json_rpc_messages() -> None:
    completed = _run_server(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05"},
            }
        ]
    )

    assert completed.returncode == 0
    stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert len(stdout_lines) == 1
    response = json.loads(stdout_lines[0])
    assert response == {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "modular-rag-mcp-server",
                "version": "0.1.0",
            },
        },
    }
    assert "MCP stdio server starting" in completed.stderr
    assert "MCP stdio server stopped" in completed.stderr


def test_mcp_server_unknown_method_returns_json_rpc_error() -> None:
    completed = _run_server(
        [{"jsonrpc": "2.0", "id": "x", "method": "missing/method"}]
    )

    response = json.loads(completed.stdout)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == "x"
    assert response["error"]["code"] == -32601
    assert "Method not found" in response["error"]["message"]
