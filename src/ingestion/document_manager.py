"""Cross-storage document lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from libs.loader import SQLiteIntegrityChecker
from libs.vector_store import ChromaStore, VectorRecord

from .storage import BM25Indexer, ImageStorage


class DocumentManagerError(ValueError):
    """Raised when document lifecycle operations cannot be completed."""


@dataclass(frozen=True)
class DocumentInfo:
    """Summary for one ingested source document."""

    doc_id: str
    source_path: str
    collection: str | None = None
    file_hash: str | None = None
    chunk_count: int = 0
    image_count: int = 0
    processed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentDetail:
    """Detailed document view with chunk and image rows."""

    info: DocumentInfo
    chunks: list[dict[str, Any]]
    images: list[dict[str, Any]]
    integrity_record: dict[str, Any] | None = None


@dataclass(frozen=True)
class DeleteResult:
    """Result of coordinated document deletion."""

    source_path: str
    collection: str | None
    file_hash: str | None
    vector_deleted: int
    bm25_deleted: int
    images_deleted: int
    integrity_deleted: int


@dataclass(frozen=True)
class CollectionStats:
    """Collection-level document statistics for dashboard services."""

    collection: str | None
    document_count: int
    chunk_count: int
    image_count: int
    sources: list[str]


class DocumentManager:
    """Coordinate document reads and deletes across vector, BM25, image, and history stores."""

    def __init__(
        self,
        chroma_store: ChromaStore,
        bm25_indexer: BM25Indexer,
        image_storage: ImageStorage,
        file_integrity: SQLiteIntegrityChecker,
    ) -> None:
        self.chroma_store = chroma_store
        self.bm25_indexer = bm25_indexer
        self.image_storage = image_storage
        self.file_integrity = file_integrity

    def list_documents(self, collection: str | None = None) -> list[DocumentInfo]:
        """Return ingested documents grouped by source path."""
        records = _filter_records(self.chroma_store.get_all(), collection=collection)
        grouped = _group_records_by_source(records)
        integrity_records = self.file_integrity.list_processed(collection=collection)
        for integrity_record in integrity_records:
            source_path = integrity_record.get("file_path")
            if source_path and source_path not in grouped:
                grouped[source_path] = []

        documents = [
            self._document_info(source_path, grouped[source_path], collection=collection)
            for source_path in sorted(grouped)
        ]
        return sorted(documents, key=lambda document: document.source_path)

    def get_document_detail(self, doc_id: str) -> DocumentDetail:
        """Return document metadata, chunks, images, and integrity row."""
        if not isinstance(doc_id, str) or not doc_id.strip():
            raise DocumentManagerError("doc_id must be a non-empty string")
        doc_id = doc_id.strip()
        info = self._find_document(doc_id)
        chunks = [
            {
                "id": record.id,
                "text": record.text,
                "metadata": dict(record.metadata),
            }
            for record in _records_for_source(self.chroma_store.get_all(), info.source_path)
        ]
        images = self.image_storage.list_images(
            collection=info.collection,
            doc_hash=info.file_hash,
        ) if info.file_hash else []
        integrity_record = (
            self.file_integrity.get_record(info.file_hash)
            if info.file_hash
            else None
        )
        return DocumentDetail(
            info=info,
            chunks=chunks,
            images=images,
            integrity_record=integrity_record,
        )

    def delete_document(
        self,
        source_path: str,
        collection: str | None = None,
    ) -> DeleteResult:
        """Delete one source document from all managed stores."""
        if not isinstance(source_path, str) or not source_path.strip():
            raise DocumentManagerError("source_path must be a non-empty string")
        source_path = source_path.strip()
        info = self._document_info(
            source_path,
            _records_for_source(self.chroma_store.get_all(), source_path),
            collection=collection,
        )
        if info.chunk_count == 0 and info.file_hash is None:
            raise DocumentManagerError(f"document not found: {source_path}")

        vector_deleted = self.chroma_store.delete_by_metadata({"source_path": source_path})
        bm25_deleted = _remove_from_bm25(
            self.bm25_indexer,
            source_path=source_path,
            collection=collection,
            file_hash=info.file_hash,
            doc_id=info.doc_id,
        )
        images_deleted = (
            self.image_storage.delete_images(collection=collection, doc_hash=info.file_hash)
            if info.file_hash
            else 0
        )
        integrity_deleted = (
            self.file_integrity.remove_record(info.file_hash)
            if info.file_hash
            else 0
        )
        return DeleteResult(
            source_path=source_path,
            collection=collection,
            file_hash=info.file_hash,
            vector_deleted=vector_deleted,
            bm25_deleted=bm25_deleted,
            images_deleted=images_deleted,
            integrity_deleted=integrity_deleted,
        )

    def get_collection_stats(self, collection: str | None = None) -> CollectionStats:
        """Return collection-level document, chunk, and image counts."""
        documents = self.list_documents(collection=collection)
        images = self.image_storage.list_images(collection=collection)
        return CollectionStats(
            collection=collection,
            document_count=len(documents),
            chunk_count=sum(document.chunk_count for document in documents),
            image_count=len(images),
            sources=[document.source_path for document in documents],
        )

    def _find_document(self, doc_id: str) -> DocumentInfo:
        for document in self.list_documents(collection=None):
            if doc_id in {
                document.doc_id,
                document.source_path,
                document.file_hash,
                Path(document.source_path).name,
            }:
                return document
        raise DocumentManagerError(f"document not found: {doc_id}")

    def _document_info(
        self,
        source_path: str,
        records: list[VectorRecord],
        collection: str | None = None,
    ) -> DocumentInfo:
        integrity = _integrity_for_source(self.file_integrity, source_path, collection)
        first_metadata = dict(records[0].metadata) if records else {}
        metadata = dict(first_metadata)
        if integrity is not None:
            metadata = {**metadata, **dict(integrity.get("metadata", {}))}
        file_hash = _first_text(
            first_metadata.get("file_hash"),
            metadata.get("file_hash"),
            None if integrity is None else integrity.get("file_hash"),
        )
        resolved_collection = collection or _first_text(
            first_metadata.get("collection"),
            metadata.get("collection"),
        )
        image_count = (
            len(self.image_storage.list_images(collection=resolved_collection, doc_hash=file_hash))
            if file_hash
            else _count_record_images(records)
        )
        return DocumentInfo(
            doc_id=_first_text(
                first_metadata.get("document_id"),
                first_metadata.get("doc_id"),
                file_hash,
                Path(source_path).stem,
            ),
            source_path=source_path,
            collection=resolved_collection,
            file_hash=file_hash,
            chunk_count=len(records),
            image_count=image_count,
            processed_at=None if integrity is None else integrity.get("processed_at"),
            metadata=metadata,
        )


def _filter_records(
    records: list[VectorRecord],
    collection: str | None = None,
) -> list[VectorRecord]:
    if collection is None:
        return records
    return [
        record
        for record in records
        if record.metadata.get("collection") in {None, collection}
    ]


def _group_records_by_source(records: list[VectorRecord]) -> dict[str, list[VectorRecord]]:
    grouped: dict[str, list[VectorRecord]] = {}
    for record in records:
        source_path = record.metadata.get("source_path")
        if isinstance(source_path, str) and source_path:
            grouped.setdefault(source_path, []).append(record)
    return grouped


def _records_for_source(records: list[VectorRecord], source_path: str) -> list[VectorRecord]:
    return [
        record
        for record in records
        if record.metadata.get("source_path") == source_path
    ]


def _integrity_for_source(
    file_integrity: SQLiteIntegrityChecker,
    source_path: str,
    collection: str | None,
) -> dict[str, Any] | None:
    records = file_integrity.list_processed(status=None, collection=collection)
    for record in records:
        if record.get("file_path") == source_path:
            return record
    return None


def _count_record_images(records: list[VectorRecord]) -> int:
    image_ids = {
        image.get("id")
        for record in records
        for image in record.metadata.get("images", [])
        if isinstance(image, dict) and image.get("id")
    }
    return len(image_ids)


def _remove_from_bm25(
    bm25_indexer: BM25Indexer,
    source_path: str,
    collection: str | None,
    file_hash: str | None,
    doc_id: str,
) -> int:
    try:
        bm25_indexer.load()
    except Exception:  # noqa: BLE001 - missing index should not block deletion.
        pass
    return bm25_indexer.remove_document(
        source_path=source_path,
        collection=collection,
        file_hash=file_hash,
        doc_id=doc_id,
    )


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None
