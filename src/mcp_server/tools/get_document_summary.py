"""get_document_summary MCP tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ingestion.storage import BM25Indexer, BM25IndexerError
from mcp_server.protocol_handler import ToolSpec


GET_DOCUMENT_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "doc_id": {
            "type": "string",
            "description": "Document id, file hash, or chunk id prefix to summarize.",
        },
    },
    "required": ["doc_id"],
    "additionalProperties": False,
}


def get_document_summary(
    arguments: dict[str, Any],
    index_dir: str | Path = "data/db/bm25",
) -> dict[str, Any]:
    """Return title, summary, and tags for an indexed document."""
    doc_id = _doc_id(arguments)
    try:
        indexer = BM25Indexer(index_dir=index_dir).load()
    except BM25IndexerError as exc:
        return _error_result(
            doc_id,
            "document_index_unavailable",
            f"Document index is unavailable: {exc}",
        )

    records = [
        dict(record)
        for record in indexer.records.values()
        if _matches_document(doc_id, record)
    ]
    if not records:
        return _error_result(
            doc_id,
            "document_not_found",
            f"Document not found: {doc_id}",
        )

    summary = _build_summary(doc_id, records)
    return {
        "content": [{"type": "text", "text": _format_summary(summary)}],
        "structuredContent": summary,
        "isError": False,
    }


def tool_spec() -> ToolSpec:
    """Return the MCP registry spec for get_document_summary."""
    return ToolSpec(
        name="get_document_summary",
        description="Return title, summary, tags, and source metadata for a document.",
        input_schema=GET_DOCUMENT_SUMMARY_SCHEMA,
        handler=get_document_summary,
    )


def _doc_id(arguments: dict[str, Any]) -> str:
    if not isinstance(arguments, dict):
        raise ValueError("get_document_summary arguments must be an object")
    doc_id = arguments.get("doc_id")
    if not isinstance(doc_id, str) or not doc_id.strip():
        raise ValueError("get_document_summary requires a non-empty doc_id")
    return doc_id.strip()


def _matches_document(doc_id: str, record: dict[str, Any]) -> bool:
    metadata = dict(record.get("metadata", {}))
    if record.get("id") == doc_id:
        return True
    if str(record.get("id", "")).startswith(f"{doc_id}_"):
        return True
    return any(
        str(metadata.get(key, "")) == doc_id
        for key in ("document_id", "doc_id", "file_hash")
    )


def _build_summary(doc_id: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    ordered_records = sorted(
        records,
        key=lambda record: (
            int(dict(record.get("metadata", {})).get("chunk_index", 0)),
            str(record.get("id", "")),
        ),
    )
    metadatas = [dict(record.get("metadata", {})) for record in ordered_records]
    first_metadata = metadatas[0]
    title = _first_metadata_value(metadatas, "title") or _fallback_title(doc_id, first_metadata)
    summary = _first_metadata_value(metadatas, "summary") or _fallback_summary(ordered_records)
    tags = _collect_tags(metadatas)

    return {
        "doc_id": doc_id,
        "title": title,
        "summary": summary,
        "tags": tags,
        "source_path": first_metadata.get("source_path", ""),
        "collection": first_metadata.get("collection"),
        "chunk_count": len(ordered_records),
    }


def _first_metadata_value(metadatas: list[dict[str, Any]], key: str) -> str:
    for metadata in metadatas:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _fallback_title(doc_id: str, metadata: dict[str, Any]) -> str:
    source_path = metadata.get("source_path")
    if isinstance(source_path, str) and source_path:
        return Path(source_path).stem
    return doc_id


def _fallback_summary(records: list[dict[str, Any]]) -> str:
    text = str(records[0].get("text", "")).strip()
    if len(text) <= 240:
        return text
    return f"{text[:237].rstrip()}..."


def _collect_tags(metadatas: list[dict[str, Any]]) -> list[str]:
    tags: list[str] = []
    for metadata in metadatas:
        raw_tags = metadata.get("tags", [])
        if isinstance(raw_tags, str):
            raw_tags = [tag.strip() for tag in raw_tags.split(",")]
        if not isinstance(raw_tags, list):
            continue
        for tag in raw_tags:
            tag_text = str(tag).strip()
            if tag_text and tag_text not in tags:
                tags.append(tag_text)
    return tags


def _format_summary(summary: dict[str, Any]) -> str:
    tags = ", ".join(summary["tags"]) if summary["tags"] else "-"
    return "\n".join(
        [
            f"# {summary['title']}",
            "",
            f"Document: {summary['doc_id']}",
            f"Source: {summary['source_path'] or '-'}",
            f"Chunks: {summary['chunk_count']}",
            f"Tags: {tags}",
            "",
            str(summary["summary"]),
        ]
    )


def _error_result(doc_id: str, code: str, message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {
            "doc_id": doc_id,
            "error": {"code": code, "message": message},
        },
        "isError": True,
    }
