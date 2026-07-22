"""Dashboard data access service."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.settings import load_settings
from ingestion import DocumentDetail, DocumentInfo, DocumentManager
from ingestion.storage import BM25Indexer, ImageStorage
from libs.loader import SQLiteIntegrityChecker
from libs.vector_store import ChromaStore


class DataService:
    """Read indexed documents and format them for dashboard pages."""

    def __init__(
        self,
        settings_path: str | Path = "config/settings.yaml",
        document_manager: DocumentManager | None = None,
    ) -> None:
        self.settings_path = Path(settings_path)
        self._document_manager = document_manager

    @property
    def document_manager(self) -> DocumentManager:
        """Return a lazily-created document manager."""
        if self._document_manager is None:
            settings = load_settings(self.settings_path)
            self._document_manager = DocumentManager(
                ChromaStore(settings.vector_store),
                BM25Indexer(),
                ImageStorage(),
                SQLiteIntegrityChecker(),
            )
        return self._document_manager

    def list_collections(self) -> list[str]:
        """Return collection names observed in indexed documents."""
        collections = {
            document.collection
            for document in self.document_manager.list_documents(collection=None)
            if document.collection
        }
        return sorted(collections)

    def list_documents(
        self,
        collection: str | None = None,
        query: str = "",
    ) -> list[dict[str, Any]]:
        """Return display rows for document list views."""
        documents = self.document_manager.list_documents(collection=collection)
        query = query.strip().lower()
        if query:
            documents = [
                document
                for document in documents
                if _document_matches_query(document, query)
            ]
        return [_document_row(document) for document in documents]

    def get_document_detail(self, doc_id: str) -> dict[str, Any]:
        """Return one document detail formatted for page rendering."""
        return _detail_payload(self.document_manager.get_document_detail(doc_id))

    def collection_stats(self, collection: str | None = None) -> dict[str, Any]:
        """Return collection-level stats as a plain dictionary."""
        return asdict(self.document_manager.get_collection_stats(collection=collection))


def _document_row(document: DocumentInfo) -> dict[str, Any]:
    return {
        "doc_id": document.doc_id,
        "source_path": document.source_path,
        "source_name": Path(document.source_path).name,
        "collection": document.collection or "",
        "file_hash": document.file_hash or "",
        "chunk_count": document.chunk_count,
        "image_count": document.image_count,
        "processed_at": document.processed_at or "",
    }


def _detail_payload(detail: DocumentDetail) -> dict[str, Any]:
    return {
        "info": _document_row(detail.info),
        "metadata": dict(detail.info.metadata),
        "chunks": [_chunk_payload(chunk) for chunk in detail.chunks],
        "images": [dict(image) for image in detail.images],
        "integrity_record": detail.integrity_record,
    }


def _chunk_payload(chunk: dict[str, Any]) -> dict[str, Any]:
    text = str(chunk.get("text", ""))
    return {
        "id": str(chunk.get("id", "")),
        "text": text,
        "preview": _preview(text),
        "metadata": dict(chunk.get("metadata", {})),
        "image_refs": list(dict(chunk.get("metadata", {})).get("image_refs", [])),
    }


def _document_matches_query(document: DocumentInfo, query: str) -> bool:
    haystack = " ".join(
        value
        for value in [
            document.doc_id,
            document.source_path,
            document.collection or "",
            document.file_hash or "",
            str(document.metadata.get("title", "")),
            str(document.metadata.get("summary", "")),
        ]
        if value
    ).lower()
    return query in haystack


def _preview(text: str, limit: int = 160) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."
