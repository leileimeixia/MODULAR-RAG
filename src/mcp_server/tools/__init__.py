"""MCP tool definitions."""

from .query_knowledge_hub import query_knowledge_hub, tool_spec as query_knowledge_hub_spec

__all__ = [
    "default_tools",
    "query_knowledge_hub",
    "query_knowledge_hub_spec",
]


def default_tools():
    """Return tool specs registered by the MCP server."""
    return [query_knowledge_hub_spec()]
