"""Tests for MCP response construction."""

from __future__ import annotations

from core import RetrievalResult
from core.response import CitationGenerator, ResponseBuilder


def _result(chunk_id: str, score: float, page: int | None = None) -> RetrievalResult:
    metadata = {"source_path": f"docs/{chunk_id}.md"}
    if page is not None:
        metadata["page"] = page
    return RetrievalResult(
        chunk_id=chunk_id,
        score=score,
        text=f"{chunk_id} detailed answer text",
        metadata=metadata,
    )


def test_citation_generator_extracts_structured_citations() -> None:
    citations = CitationGenerator().generate([_result("a", 0.9, page=2)])

    assert citations == [
        {
            "index": 1,
            "source": "docs/a.md",
            "page": 2,
            "chunk_id": "a",
            "score": 0.9,
        }
    ]


def test_response_builder_returns_markdown_and_structured_citations() -> None:
    response = ResponseBuilder().build(
        [_result("a", 0.9, page=2), _result("b", 0.7)],
        query="alpha",
    )

    markdown = response["content"][0]["text"]
    assert response["isError"] is False
    assert "找到 2 条" in markdown
    assert "### [1] a" in markdown
    assert "引用：[1]" in markdown
    assert response["structuredContent"]["query"] == "alpha"
    assert [item["chunk_id"] for item in response["structuredContent"]["citations"]] == [
        "a",
        "b",
    ]


def test_response_builder_returns_friendly_message_for_no_results() -> None:
    response = ResponseBuilder().build([], query="missing")

    assert "未找到" in response["content"][0]["text"]
    assert response["structuredContent"]["citations"] == []
