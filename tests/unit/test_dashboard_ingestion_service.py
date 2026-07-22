"""Tests for dashboard ingestion management service."""

from __future__ import annotations

import pytest

from core.trace import TraceContext
from ingestion import DeleteResult, DocumentInfo, IngestionResult
from observability.dashboard.services.ingestion_service import (
    IngestionService,
    IngestionServiceError,
)


def test_ingestion_service_saves_upload_and_runs_pipeline(tmp_path) -> None:
    pipeline = _FakePipeline()
    service = IngestionService(
        documents_root=tmp_path / "documents",
        pipeline=pipeline,
        document_manager=_FakeDocumentManager(),
    )
    progress = []

    result = service.ingest_upload(
        _Upload("guide.pdf", b"%PDF fake"),
        collection="docs",
        force=True,
        on_progress=lambda stage, current, total: progress.append((stage, current, total)),
    )

    assert (tmp_path / "documents" / "docs" / "guide.pdf").read_bytes() == b"%PDF fake"
    assert pipeline.calls[0]["collection"] == "docs"
    assert pipeline.calls[0]["force"] is True
    assert result["chunk_count"] == 2
    assert result["progress_events"] == [
        {"stage": "load", "current": 1, "total": 2},
        {"stage": "complete", "current": 2, "total": 2},
    ]
    assert progress == [("load", 1, 2), ("complete", 2, 2)]


def test_ingestion_service_rejects_invalid_upload_inputs(tmp_path) -> None:
    service = IngestionService(
        documents_root=tmp_path / "documents",
        pipeline=_FakePipeline(),
        document_manager=_FakeDocumentManager(),
    )

    with pytest.raises(IngestionServiceError, match="unsupported"):
        service.ingest_upload(_Upload("bad.exe", b"bytes"), collection="docs")
    with pytest.raises(IngestionServiceError, match="path separators"):
        service.ingest_upload(_Upload("guide.pdf", b"bytes"), collection="../bad")
    with pytest.raises(IngestionServiceError, match="bytes"):
        service.ingest_upload(_Upload("guide.pdf", b""), collection="docs")


def test_ingestion_service_lists_and_deletes_documents() -> None:
    manager = _FakeDocumentManager()
    service = IngestionService(
        pipeline=_FakePipeline(),
        document_manager=manager,
    )

    documents = service.list_documents(collection="docs")
    result = service.delete_document("docs/guide.pdf", collection="docs")

    assert documents[0]["source_name"] == "guide.pdf"
    assert result["vector_deleted"] == 2
    assert manager.deleted == [("docs/guide.pdf", "docs")]


class _Upload:
    def __init__(self, name: str, payload: bytes) -> None:
        self.name = name
        self._payload = payload

    def getvalue(self) -> bytes:
        return self._payload


class _FakePipeline:
    def __init__(self) -> None:
        self.calls = []

    def run(self, path, collection="default", force=False, on_progress=None):
        self.calls.append(
            {
                "path": str(path),
                "collection": collection,
                "force": force,
            }
        )
        if on_progress is not None:
            on_progress("load", 1, 2)
            on_progress("complete", 2, 2)
        return IngestionResult(
            file_hash="hash-1",
            document_id="doc-1",
            skipped=False,
            chunk_count=2,
            record_count=2,
            vector_ids=["chunk-1", "chunk-2"],
            image_count=1,
            trace=TraceContext(trace_id="trace-1"),
        )


class _FakeDocumentManager:
    def __init__(self) -> None:
        self.deleted = []

    def list_documents(self, collection=None):
        return [
            DocumentInfo(
                doc_id="doc-1",
                source_path="docs/guide.pdf",
                collection="docs",
                file_hash="hash-1",
                chunk_count=2,
                image_count=1,
            )
        ]

    def delete_document(self, source_path, collection=None):
        self.deleted.append((source_path, collection))
        return DeleteResult(
            source_path=source_path,
            collection=collection,
            file_hash="hash-1",
            vector_deleted=2,
            bm25_deleted=2,
            images_deleted=1,
            integrity_deleted=1,
        )
