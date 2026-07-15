"""Tests for the list_collections MCP tool."""

from __future__ import annotations

import pytest

from mcp_server.tools.list_collections import list_collections, tool_spec


def test_list_collections_returns_sorted_collection_stats(tmp_path) -> None:
    documents_root = tmp_path / "documents"
    alpha = documents_root / "alpha"
    beta = documents_root / "beta"
    (alpha / "nested").mkdir(parents=True)
    beta.mkdir(parents=True)
    (alpha / "a.txt").write_text("hello", encoding="utf-8")
    (alpha / "nested" / "b.md").write_text("world!", encoding="utf-8")
    (beta / "empty.keep").write_text("", encoding="utf-8")

    result = list_collections({}, documents_root=documents_root)

    collections = result["structuredContent"]["collections"]
    assert [collection["name"] for collection in collections] == ["alpha", "beta"]
    assert collections[0]["document_count"] == 2
    assert collections[0]["total_bytes"] == 11
    assert collections[1]["document_count"] == 1
    assert collections[1]["total_bytes"] == 0
    assert "alpha: documents=2, bytes=11" in result["content"][0]["text"]


def test_list_collections_returns_empty_result_for_missing_root(tmp_path) -> None:
    missing_root = tmp_path / "missing"

    result = list_collections({}, documents_root=missing_root)

    assert result["structuredContent"]["collections"] == []
    assert f"No document collections found under {missing_root}." == result["content"][0]["text"]


def test_list_collections_rejects_non_object_arguments(tmp_path) -> None:
    with pytest.raises(ValueError, match="arguments must be an object"):
        list_collections([], documents_root=tmp_path)  # type: ignore[arg-type]


def test_tool_spec_exposes_mcp_schema() -> None:
    spec = tool_spec()

    assert spec.name == "list_collections"
    assert spec.schema()["inputSchema"]["additionalProperties"] is False
