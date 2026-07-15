"""list_collections MCP tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp_server.protocol_handler import ToolSpec


LIST_COLLECTIONS_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def list_collections(
    arguments: dict[str, Any],
    documents_root: str | Path = "data/documents",
) -> dict[str, Any]:
    """List document collections under the configured documents root."""
    if not isinstance(arguments, dict):
        raise ValueError("list_collections arguments must be an object")

    root = Path(documents_root)
    collections = _collection_stats(root)
    return {
        "content": [{"type": "text", "text": _format_collections(root, collections)}],
        "structuredContent": {
            "root": str(root),
            "collections": collections,
        },
        "isError": False,
    }


def tool_spec() -> ToolSpec:
    """Return the MCP registry spec for list_collections."""
    return ToolSpec(
        name="list_collections",
        description="List local document collections and basic file statistics.",
        input_schema=LIST_COLLECTIONS_SCHEMA,
        handler=list_collections,
    )


def _collection_stats(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    if not root.is_dir():
        raise ValueError(f"documents root is not a directory: {root}")

    collections: list[dict[str, Any]] = []
    for collection_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        files = [path for path in collection_dir.rglob("*") if path.is_file()]
        collections.append(
            {
                "name": collection_dir.name,
                "path": str(collection_dir),
                "document_count": len(files),
                "total_bytes": sum(path.stat().st_size for path in files),
            }
        )
    return collections


def _format_collections(root: Path, collections: list[dict[str, Any]]) -> str:
    if not collections:
        return f"No document collections found under {root}."

    lines = [f"Document collections under {root}:"]
    lines.extend(
        "- {name}: documents={document_count}, bytes={total_bytes}".format(
            **collection
        )
        for collection in collections
    )
    return "\n".join(lines)
