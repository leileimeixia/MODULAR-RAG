"""Tests for MCP JSON-RPC protocol handling."""

from __future__ import annotations

from mcp_server.protocol_handler import ProtocolHandler, ToolSpec


def test_initialize_returns_server_info_and_tool_capabilities() -> None:
    response = ProtocolHandler().handle_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
    )

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


def test_tools_list_returns_registered_tool_schemas() -> None:
    handler = ProtocolHandler(
        [
            ToolSpec(
                name="echo",
                description="Echo input text.",
                input_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                },
                handler=lambda arguments: arguments["text"],
            )
        ]
    )

    response = handler.handle_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    )

    assert response == {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {
            "tools": [
                {
                    "name": "echo",
                    "description": "Echo input text.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                    },
                }
            ]
        },
    }


def test_tools_call_routes_to_registered_tool() -> None:
    handler = ProtocolHandler(
        [
            ToolSpec(
                name="echo",
                description="Echo input text.",
                input_schema={"type": "object"},
                handler=lambda arguments: {"echo": arguments["text"]},
            )
        ]
    )

    response = handler.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "echo", "arguments": {"text": "hello"}},
        }
    )

    assert response == {
        "jsonrpc": "2.0",
        "id": 3,
        "result": {
            "content": [{"type": "text", "text": '{"echo": "hello"}'}],
            "isError": False,
        },
    }


def test_notification_returns_no_response() -> None:
    assert ProtocolHandler().handle_message(
        {"jsonrpc": "2.0", "method": "notifications/initialized"}
    ) is None


def test_invalid_request_returns_json_rpc_error() -> None:
    response = ProtocolHandler().handle_message({"jsonrpc": "2.0", "id": 4})

    assert response == {
        "jsonrpc": "2.0",
        "id": 4,
        "error": {"code": -32600, "message": "Invalid Request"},
    }


def test_unknown_method_returns_method_not_found() -> None:
    response = ProtocolHandler().handle_message(
        {"jsonrpc": "2.0", "id": 5, "method": "missing"}
    )

    assert response["error"]["code"] == -32601
    assert "Method not found" in response["error"]["message"]


def test_tools_call_rejects_invalid_params() -> None:
    response = ProtocolHandler().handle_message(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "missing", "arguments": []},
        }
    )

    assert response["error"]["code"] == -32602
    assert "arguments" in response["error"]["message"]
