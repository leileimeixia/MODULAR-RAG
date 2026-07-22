"""Tests for dashboard data browsing service."""

from __future__ import annotations

from ingestion import CollectionStats, DocumentDetail, DocumentInfo
from observability.dashboard.services.data_service import DataService


def test_data_service_lists_collections_and_documents() -> None:
    service = DataService(document_manager=_FakeDocumentManager())

    assert service.list_collections() == ["docs"]
    rows = service.list_documents(collection="docs", query="guide")

    assert rows == [
        {
            "doc_id": "doc-1",
            "source_path": "docs/guide.pdf",
            "source_name": "guide.pdf",
            "collection": "docs",
            "file_hash": "hash-1",
            "chunk_count": 2,
            "image_count": 1,
            "processed_at": "2026-07-22T00:00:00Z",
        }
    ]


def test_data_service_formats_document_detail() -> None:
    service = DataService(document_manager=_FakeDocumentManager())

    detail = service.get_document_detail("doc-1")

    assert detail["info"]["source_name"] == "guide.pdf"
    assert detail["chunks"][0]["preview"] == "alpha beta"
    assert detail["chunks"][0]["image_refs"] == ["img-1"]
    assert detail["images"][0]["image_id"] == "img-1"
    assert detail["integrity_record"]["file_hash"] == "hash-1"


class _FakeDocumentManager:
    def __init__(self) -> None:
        self.document = DocumentInfo(
            doc_id="doc-1",
            source_path="docs/guide.pdf",
            collection="docs",
            file_hash="hash-1",
            chunk_count=2,
            image_count=1,
            processed_at="2026-07-22T00:00:00Z",
            metadata={"title": "Guide"},
        )

    def list_documents(self, collection=None):
        if collection not in {None, "docs"}:
            return []
        return [self.document]

    def get_document_detail(self, doc_id):
        return DocumentDetail(
            info=self.document,
            chunks=[
                {
                    "id": "chunk-1",
                    "text": "alpha beta",
                    "metadata": {
                        "source_path": "docs/guide.pdf",
                        "image_refs": ["img-1"],
                    },
                }
            ],
            images=[
                {
                    "image_id": "img-1",
                    "file_path": "images/img-1.png",
                    "collection": "docs",
                    "doc_hash": "hash-1",
                }
            ],
            integrity_record={"file_hash": "hash-1"},
        )

    def get_collection_stats(self, collection=None):
        return CollectionStats(
            collection=collection,
            document_count=1,
            chunk_count=2,
            image_count=1,
            sources=["docs/guide.pdf"],
        )
