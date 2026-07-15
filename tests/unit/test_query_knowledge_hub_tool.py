"""Tests for the query_knowledge_hub MCP tool."""

from __future__ import annotations

import pytest

from core import RetrievalResult
from mcp_server.tools.query_knowledge_hub import query_knowledge_hub, tool_spec


class FakeHybridSearch:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, query: str, top_k: int, filters=None):
        self.calls.append({"query": query, "top_k": top_k, "filters": filters or {}})
        return [
            RetrievalResult(
                chunk_id="chunk-a",
                score=0.4,
                text="candidate text",
                metadata={"source_path": "docs/a.md", "collection": "docs"},
            )
        ]


class FakeReranker:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def rerank(self, query: str, candidates, top_k: int):
        self.calls.append(
            {
                "query": query,
                "candidate_ids": [candidate.chunk_id for candidate in candidates],
                "top_k": top_k,
            }
        )
        return [
            RetrievalResult(
                chunk_id="chunk-a",
                score=0.9,
                text="reranked text",
                metadata={"source_path": "docs/a.md", "page": 3},
            )
        ]


def test_tool_spec_exposes_query_knowledge_hub_schema() -> None:
    spec = tool_spec()

    assert spec.name == "query_knowledge_hub"
    assert spec.schema()["inputSchema"]["required"] == ["query"]


def test_query_knowledge_hub_calls_search_rerank_and_builds_citations() -> None:
    search = FakeHybridSearch()
    reranker = FakeReranker()

    response = query_knowledge_hub(
        {"query": " alpha ", "top_k": 2, "collection": "docs"},
        settings=object(),
        hybrid_search=search,
        reranker=reranker,
    )

    assert search.calls == [
        {"query": "alpha", "top_k": 2, "filters": {"collection": "docs"}}
    ]
    assert reranker.calls == [
        {"query": "alpha", "candidate_ids": ["chunk-a"], "top_k": 2}
    ]
    assert response["content"][0]["type"] == "text"
    assert response["structuredContent"]["citations"] == [
        {
            "index": 1,
            "source": "docs/a.md",
            "page": 3,
            "chunk_id": "chunk-a",
            "score": 0.9,
        }
    ]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({}, "query"),
        ({"query": " "}, "query"),
        ({"query": "alpha", "top_k": 0}, "top_k"),
        ({"query": "alpha", "collection": ""}, "collection"),
    ],
)
def test_query_knowledge_hub_rejects_invalid_arguments(arguments, message) -> None:
    with pytest.raises(ValueError, match=message):
        query_knowledge_hub(arguments, settings=object())
