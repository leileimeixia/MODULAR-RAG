"""Tests for the query_knowledge_hub MCP tool."""

from __future__ import annotations

import pytest

from core import RetrievalResult
from core.trace import TraceCollector
from mcp_server.tools.query_knowledge_hub import query_knowledge_hub, tool_spec


class FakeHybridSearch:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def search(self, query: str, top_k: int, filters=None, trace=None):
        self.calls.append(
            {
                "query": query,
                "top_k": top_k,
                "filters": filters or {},
                "trace_type": getattr(trace, "trace_type", None),
            }
        )
        if trace is not None:
            trace.record_stage("query_processing", method="FakeHybridSearch", elapsed_ms=1)
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

    def rerank(self, query: str, candidates, top_k: int, trace=None):
        self.calls.append(
            {
                "query": query,
                "candidate_ids": [candidate.chunk_id for candidate in candidates],
                "top_k": top_k,
                "trace_type": getattr(trace, "trace_type", None),
            }
        )
        if trace is not None:
            trace.record_stage("rerank", method="FakeReranker", elapsed_ms=2)
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
    trace_collector = TraceCollector()

    response = query_knowledge_hub(
        {"query": " alpha ", "top_k": 2, "collection": "docs"},
        settings=object(),
        hybrid_search=search,
        reranker=reranker,
        trace_collector=trace_collector,
    )

    assert search.calls == [
        {
            "query": "alpha",
            "top_k": 2,
            "filters": {"collection": "docs"},
            "trace_type": "query",
        }
    ]
    assert reranker.calls == [
        {
            "query": "alpha",
            "candidate_ids": ["chunk-a"],
            "top_k": 2,
            "trace_type": "query",
        }
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
    trace_payload = response["structuredContent"]["trace"]
    assert trace_payload["trace_type"] == "query"
    assert [stage["name"] for stage in trace_payload["stages"]] == [
        "query_processing",
        "rerank",
    ]
    assert trace_collector.traces == [trace_payload]


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
