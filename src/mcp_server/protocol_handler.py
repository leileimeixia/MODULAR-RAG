"""JSON-RPC protocol handling for MCP messages."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


SERVER_NAME = "modular-rag-mcp-server"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOL_VERSION = "2024-11-05"


JsonObject = dict[str, Any]
ToolHandler = Callable[[JsonObject], Any]


@dataclass(frozen=True)
class ToolSpec:
    """Registered MCP tool schema and callable."""

    name: str
    description: str
    input_schema: JsonObject
    handler: ToolHandler

    def schema(self) -> JsonObject:
        """Return the schema shape exposed by tools/list."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
        }


class ProtocolHandler:
    """Handle JSON-RPC 2.0 requests for the MCP server."""

    def __init__(self, tools: list[ToolSpec] | None = None) -> None:
        self.tools = {tool.name: tool for tool in (tools or [])}

    def handle_message(self, message: Any) -> JsonObject | None:
        """Return a JSON-RPC response for one decoded request."""
        if not isinstance(message, dict):
            return error_response(None, -32600, "Invalid Request")
        request_id = message.get("id")
        if message.get("jsonrpc") != "2.0" or "method" not in message:
            return error_response(request_id, -32600, "Invalid Request")

        method = message["method"]
        if not isinstance(method, str) or not method:
            return error_response(request_id, -32600, "Invalid Request")
        if request_id is None and method.startswith("notifications/"):
            return None

        try:
            result = self._dispatch(method, message.get("params", {}))
        except ProtocolError as exc:
            return error_response(request_id, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001 - protocol boundary maps failures.
            return error_response(request_id, -32603, f"Internal error: {exc}")

        if request_id is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _dispatch(self, method: str, params: Any) -> JsonObject:
        if method == "initialize":
            return self.handle_initialize(params)
        if method == "tools/list":
            return self.handle_tools_list()
        if method == "tools/call":
            return self.handle_tools_call(params)
        raise ProtocolError(-32601, f"Method not found: {method}")

    def handle_initialize(self, params: Any) -> JsonObject:
        """Return server metadata and declared capabilities."""
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

    def handle_tools_list(self) -> JsonObject:
        """Return schemas for registered tools."""
        return {"tools": [tool.schema() for tool in self.tools.values()]}

    def handle_tools_call(self, params: Any) -> JsonObject:
        """Route a tools/call request to the registered tool callable."""
        if not isinstance(params, dict):
            raise ProtocolError(-32602, "tools/call params must be an object")
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not name:
            raise ProtocolError(-32602, "tools/call params.name must be a non-empty string")
        if not isinstance(arguments, dict):
            raise ProtocolError(-32602, "tools/call params.arguments must be an object")
        tool = self.tools.get(name)
        if tool is None:
            raise ProtocolError(-32602, f"Unknown tool: {name}")
        return _tool_result(tool.handler(arguments))


class ProtocolError(ValueError):
    """A JSON-RPC error with a protocol code."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def error_response(request_id: Any, code: int, message: str) -> JsonObject:
    """Return a JSON-RPC error response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def parse_error_response(message: str = "Parse error") -> JsonObject:
    """Return a JSON-RPC parse error response."""
    return error_response(None, -32700, message)


def _tool_result(result: Any) -> JsonObject:
    if isinstance(result, dict) and "content" in result:
        return result
    text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}], "isError": False}
