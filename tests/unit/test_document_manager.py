"""Tests for cross-storage document lifecycle management."""

from __future__ import annotations

import pytest

from core import ChunkRecord
from ingestion import DocumentManager, DocumentManagerError
from ingestion.storage import BM25Indexer, ImageStorage
from libs.loader import SQLiteIntegrityChecker
from libs.vector_store import ChromaStore, VectorRecord
from core.settings import VectorStoreSettings


def test_document_manager_lists_documents_with_stats(tmp_path) -> None:
    manager, stores = _manager(tmp_path)
    _seed_document(stores, tmp_path, source_name="guide.pdf", chunk_count=2)

    documents = manager.list_documents(collection="docs")

    assert len(documents) == 1
    assert documents[0].source_path.endswith("guide.pdf")
    assert documents[0].collection == "docs"
    assert documents[0].chunk_count == 2
    assert documents[0].image_count == 1
    assert documents[0].metadata["record_count"] == 2


def test_document_manager_returns_document_detail(tmp_path) -> None:
    manager, stores = _manager(tmp_path)
    source_path = _seed_document(stores, tmp_path, source_name="guide.pdf", chunk_count=2)

    detail = manager.get_document_detail(source_path)

    assert detail.info.source_path == source_path
    assert [chunk["id"] for chunk in detail.chunks] == ["doc-hash-0000", "doc-hash-0001"]
    assert [image["image_id"] for image in detail.images] == ["img-doc-hash"]
    assert detail.integrity_record is not None
    assert detail.integrity_record["metadata"]["collection"] == "docs"


def test_document_manager_deletes_document_across_stores(tmp_path) -> None:
    manager, stores = _manager(tmp_path)
    source_path = _seed_document(stores, tmp_path, source_name="guide.pdf", chunk_count=2)
    _seed_document(stores, tmp_path, source_name="other.pdf", file_hash="other-hash", chunk_count=1)

    result = manager.delete_document(source_path, collection="docs")

    assert result.vector_deleted == 2
    assert result.bm25_deleted == 2
    assert result.images_deleted == 1
    assert result.integrity_deleted == 1
    assert [record.metadata["source_path"] for record in stores["chroma"].get_all()] == [
        str(tmp_path / "other.pdf")
    ]
    assert all(
        not result["chunk_id"].startswith("doc-hash")
        for result in stores["bm25"].query("guide")
    )
    assert stores["bm25"].query("other")
    assert stores["integrity"].get_record("doc-hash") is None
    assert stores["images"].list_images(doc_hash="doc-hash") == []


def test_document_manager_collection_stats(tmp_path) -> None:
    manager, stores = _manager(tmp_path)
    _seed_document(stores, tmp_path, source_name="guide.pdf", chunk_count=2)
    _seed_document(stores, tmp_path, source_name="other.pdf", file_hash="other-hash", chunk_count=1)

    stats = manager.get_collection_stats(collection="docs")

    assert stats.document_count == 2
    assert stats.chunk_count == 3
    assert stats.image_count == 2
    assert len(stats.sources) == 2


def test_document_manager_raises_for_missing_document(tmp_path) -> None:
    manager, _stores = _manager(tmp_path)

    with pytest.raises(DocumentManagerError, match="document not found"):
        manager.delete_document("missing.pdf")


def test_document_manager_rejects_blank_document_inputs(tmp_path) -> None:
    manager, _stores = _manager(tmp_path)

    with pytest.raises(DocumentManagerError, match="doc_id must be a non-empty string"):
        manager.get_document_detail(" ")

    with pytest.raises(DocumentManagerError, match="source_path must be a non-empty string"):
        manager.delete_document(" ")


def _manager(tmp_path):
    chroma = ChromaStore(
        VectorStoreSettings(
            provider="chroma",
            persist_directory=str(tmp_path / "vectors"),
            collection_name="test",
        )
    )
    bm25 = BM25Indexer(index_dir=tmp_path / "bm25")
    images = ImageStorage(
        image_root=tmp_path / "images",
        db_path=tmp_path / "db" / "image_index.db",
    )
    integrity = SQLiteIntegrityChecker(tmp_path / "db" / "ingestion_history.db")
    stores = {
        "chroma": chroma,
        "bm25": bm25,
        "images": images,
        "integrity": integrity,
    }
    return DocumentManager(chroma, bm25, images, integrity), stores


def _seed_document(
    stores,
    tmp_path,
    source_name: str,
    file_hash: str = "doc-hash",
    chunk_count: int = 1,
) -> str:
    source_path = str(tmp_path / source_name)
    records = [
        VectorRecord(
            id=f"{file_hash}-{index:04d}",
            text=f"{source_name} guide text {index}",
            vector=[1.0, float(index)],
            metadata={
                "source_path": source_path,
                "file_hash": file_hash,
                "collection": "docs",
                "chunk_index": index,
            },
        )
        for index in range(chunk_count)
    ]
    stores["chroma"].upsert(records)
    stores["bm25"].add(
        [
            ChunkRecord(
                id=record.id,
                text=record.text,
                metadata=record.metadata,
                sparse_vector={
                    "guide": 1.0,
                    source_name.split(".")[0]: 1.0,
                },
            )
            for record in records
        ]
    )
    stores["images"].save_image(
        f"img-{file_hash}",
        b"image-bytes",
        collection="docs",
        doc_hash=file_hash,
    )
    stores["integrity"].mark_success(
        file_hash,
        source_path,
        metadata={
            "collection": "docs",
            "record_count": chunk_count,
        },
    )
    return source_path
