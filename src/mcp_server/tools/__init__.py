"""MCP tool definitions."""

from .list_collections import list_collections, tool_spec as list_collections_spec
from .query_knowledge_hub import query_knowledge_hub, tool_spec as query_knowledge_hub_spec

__all__ = [
    "default_tools",
    "list_collections",
    "list_collections_spec",
    "query_knowledge_hub",
    "query_knowledge_hub_spec",
]


def default_tools():
    """Return tool specs registered by the MCP server."""
    return [query_knowledge_hub_spec(), list_collections_spec()]
