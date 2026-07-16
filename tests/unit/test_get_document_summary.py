"""Tests for the get_document_summary MCP tool."""

from __future__ import annotations

import pytest

from core import ChunkRecord
from ingestion.storage import BM25Indexer
from mcp_server.tools.get_document_summary import get_document_summary, tool_spec


def _record(
    chunk_id: str,
    text: str,
    metadata: dict,
) -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id,
        text=text,
        metadata={"source_path": "docs/source.md", **metadata},
        sparse_vector={"term": 1.0},
    )


def test_get_document_summary_returns_metadata_from_index(tmp_path) -> None:
    BM25Indexer(index_dir=tmp_path).build(
        [
            _record(
                "doc-1_0001_bbbb",
                "second chunk",
                {
                    "document_id": "doc-1",
                    "chunk_index": 1,
                    "summary": "Second summary.",
                    "tags": ["later"],
                },
            ),
            _record(
                "doc-1_0000_aaaa",
                "first chunk",
                {
                    "document_id": "doc-1",
                    "chunk_index": 0,
                    "title": "Document Title",
                    "summary": "Document summary.",
                    "tags": ["rag", "summary"],
                    "collection": "docs",
                },
            ),
            _record("other_0000_cccc", "other", {"document_id": "other"}),
        ]
    )

    result = get_document_summary({"doc_id": "doc-1"}, index_dir=tmp_path)

    payload = result["structuredContent"]
    assert result["isError"] is False
    assert payload == {
        "doc_id": "doc-1",
        "title": "Document Title",
        "summary": "Document summary.",
        "tags": ["rag", "summary", "later"],
        "source_path": "docs/source.md",
        "collection": "docs",
        "chunk_count": 2,
    }
    assert "# Document Title" in result["content"][0]["text"]


def test_get_document_summary_matches_file_hash_metadata(tmp_path) -> None:
    BM25Indexer(index_dir=tmp_path).build(
        [
            _record(
                "hash-1_0000_abcd",
                "fallback body",
                {"file_hash": "hash-1", "chunk_index": 0, "tags": "pdf, manual"},
            )
        ]
    )

    result = get_document_summary({"doc_id": "hash-1"}, index_dir=tmp_path)

    assert result["structuredContent"]["title"] == "source"
    assert result["structuredContent"]["summary"] == "fallback body"
    assert result["structuredContent"]["tags"] == ["pdf", "manual"]


def test_get_document_summary_returns_tool_error_for_missing_doc(tmp_path) -> None:
    BM25Indexer(index_dir=tmp_path).build(
        [_record("doc-1_0000_abcd", "body", {"document_id": "doc-1"})]
    )

    result = get_document_summary({"doc_id": "missing"}, index_dir=tmp_path)

    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "document_not_found"
    assert "Document not found: missing" in result["content"][0]["text"]


def test_get_document_summary_returns_tool_error_for_missing_index(tmp_path) -> None:
    result = get_document_summary({"doc_id": "doc-1"}, index_dir=tmp_path)

    assert result["isError"] is True
    assert result["structuredContent"]["error"]["code"] == "document_index_unavailable"


def test_get_document_summary_rejects_invalid_arguments(tmp_path) -> None:
    with pytest.raises(ValueError, match="non-empty doc_id"):
        get_document_summary({"doc_id": ""}, index_dir=tmp_path)


def test_tool_spec_exposes_mcp_schema() -> None:
    spec = tool_spec()

    assert spec.name == "get_document_summary"
    assert spec.schema()["inputSchema"]["required"] == ["doc_id"]
