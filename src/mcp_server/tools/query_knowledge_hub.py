"""query_knowledge_hub MCP tool."""

from __future__ import annotations

from typing import Any

from core.query_engine import CoreReranker, HybridSearch
from core.response import ResponseBuilder
from core.settings import load_settings
from mcp_server.protocol_handler import ToolSpec


QUERY_KNOWLEDGE_HUB_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Natural-language question or search text.",
        },
        "top_k": {
            "type": "integer",
            "minimum": 1,
            "default": 5,
            "description": "Maximum number of cited chunks to return.",
        },
        "collection": {
            "type": "string",
            "description": "Optional collection metadata filter.",
        },
    },
    "required": ["query"],
}


def query_knowledge_hub(
    arguments: dict[str, Any],
    settings: Any | None = None,
    hybrid_search: HybridSearch | None = None,
    reranker: CoreReranker | None = None,
    response_builder: ResponseBuilder | None = None,
) -> dict[str, Any]:
    """Run hybrid search and rerank, then return an MCP tool result."""
    query = _query(arguments)
    top_k = _top_k(arguments)
    filters = _filters(arguments)
    settings = settings or load_settings()
    hybrid_search = hybrid_search or HybridSearch(settings=settings)
    reranker = reranker or CoreReranker(settings=settings)
    response_builder = response_builder or ResponseBuilder()

    candidates = hybrid_search.search(query, top_k=top_k, filters=filters)
    results = reranker.rerank(query, candidates, top_k=top_k)
    return response_builder.build(results, query)


def tool_spec() -> ToolSpec:
    """Return the MCP registry spec for query_knowledge_hub."""
    return ToolSpec(
        name="query_knowledge_hub",
        description="Search the local RAG knowledge hub and return cited chunks.",
        input_schema=QUERY_KNOWLEDGE_HUB_SCHEMA,
        handler=query_knowledge_hub,
    )


def _query(arguments: dict[str, Any]) -> str:
    if not isinstance(arguments, dict):
        raise ValueError("query_knowledge_hub arguments must be an object")
    query = arguments.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query_knowledge_hub requires a non-empty query")
    return query.strip()


def _top_k(arguments: dict[str, Any]) -> int:
    raw_top_k = arguments.get("top_k", 5)
    if not isinstance(raw_top_k, int) or raw_top_k <= 0:
        raise ValueError("query_knowledge_hub top_k must be a positive integer")
    return raw_top_k


def _filters(arguments: dict[str, Any]) -> dict[str, Any]:
    collection = arguments.get("collection")
    if collection is None:
        return {}
    if not isinstance(collection, str) or not collection.strip():
        raise ValueError("query_knowledge_hub collection must be a non-empty string")
    return {"collection": collection.strip()}
