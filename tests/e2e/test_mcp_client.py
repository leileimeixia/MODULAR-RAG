"""E2E-style MCP client tests over the stdio JSON-RPC loop."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


SERVER_BOOTSTRAP = r"""
import sys
from pathlib import Path

project_root = Path.cwd()
src_root = project_root / "src"
sys.path.insert(0, str(src_root))

from mcp_server.protocol_handler import ToolSpec
from mcp_server import server


def fake_query_knowledge_hub(arguments):
    query = arguments["query"]
    return {
        "content": [
            {
                "type": "text",
                "text": f"Answer for {query}\n\nCitations:\n[1] docs/guide.md#chunk-a",
            }
        ],
        "structuredContent": {
            "answer": f"Answer for {query}",
            "citations": [
                {
                    "chunk_id": "chunk-a",
                    "source_path": "docs/guide.md",
                    "score": 0.95,
                }
            ],
        },
        "isError": False,
    }


def fake_default_tools():
    return [
        ToolSpec(
            name="query_knowledge_hub",
            description="Search the local RAG knowledge hub and return cited chunks.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            handler=fake_query_knowledge_hub,
        )
    ]


server.default_tools = fake_default_tools
raise SystemExit(server.main())
"""


def test_mcp_client_lists_and_calls_query_knowledge_hub() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", SERVER_BOOTSTRAP],
        cwd=PROJECT_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        initialize = _request(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "pytest-mcp-client", "version": "0.1"},
                },
            },
        )
        assert initialize["result"]["serverInfo"]["name"] == "modular-rag-mcp-server"
        assert initialize["result"]["capabilities"] == {"tools": {}}

        tools = _request(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
            },
        )
        assert [tool["name"] for tool in tools["result"]["tools"]] == [
            "query_knowledge_hub"
        ]

        tool_result = _request(
            process,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "query_knowledge_hub",
                    "arguments": {"query": "How do I configure Azure OpenAI?"},
                },
            },
        )

        result = tool_result["result"]
        assert result["isError"] is False
        assert "Citations:" in result["content"][0]["text"]
        assert result["structuredContent"]["citations"] == [
            {
                "chunk_id": "chunk-a",
                "source_path": "docs/guide.md",
                "score": 0.95,
            }
        ]
    finally:
        _stop_process(process)


def _request(process: subprocess.Popen, payload: dict[str, Any]) -> dict[str, Any]:
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
    process.stdin.flush()
    line = process.stdout.readline()
    if not line:
        stderr = process.stderr.read() if process.stderr is not None else ""
        raise AssertionError(f"MCP server returned no response. stderr={stderr}")
    response = json.loads(line)
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == payload["id"]
    assert "error" not in response
    return response


def _stop_process(process: subprocess.Popen) -> None:
    if process.stdin is not None:
        process.stdin.close()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
