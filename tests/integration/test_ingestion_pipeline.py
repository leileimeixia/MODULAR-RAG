"""Integration tests for the MVP ingestion pipeline orchestration."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from core import Chunk, ChunkRecord, Document
from core.trace import TraceCollector
from ingestion import IngestionPipeline, IngestionPipelineError


class FakeIntegrityChecker:
    def __init__(self, skip: bool = False) -> None:
        self.skip = skip
        self.successes: list[dict] = []
        self.failures: list[dict] = []

    def compute_sha256(self, path: str | Path) -> str:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def should_skip(self, file_hash: str) -> bool:
        return self.skip

    def mark_success(self, file_hash: str, file_path: str | Path, metadata: dict | None = None) -> None:
        self.successes.append(
            {"file_hash": file_hash, "file_path": str(file_path), "metadata": metadata or {}}
        )

    def mark_failed(
        self,
        file_hash: str,
        error_msg: str,
        file_path: str | Path | None = None,
    ) -> None:
        self.failures.append(
            {"file_hash": file_hash, "file_path": None if file_path is None else str(file_path), "error": error_msg}
        )


class FakeLoader:
    def __init__(self, document: Document | None = None, fail: bool = False) -> None:
        self.document = document
        self.fail = fail
        self.calls: list[str] = []

    def load(self, path: str | Path) -> Document:
        self.calls.append(str(path))
        if self.fail:
            raise ValueError("loader exploded")
        assert self.document is not None
        return self.document


class FakeChunker:
    def split_document(self, document: Document) -> list[Chunk]:
        return [
            Chunk(
                id=f"{document.id}-chunk-0",
                text="alpha beta",
                metadata={**document.metadata, "chunk_index": 0},
                start_offset=0,
                end_offset=10,
                source_ref=document.id,
            ),
            Chunk(
                id=f"{document.id}-chunk-1",
                text="gamma",
                metadata={**document.metadata, "chunk_index": 1},
                start_offset=11,
                end_offset=16,
                source_ref=document.id,
            ),
        ]


class FakeTransform:
    def __init__(self) -> None:
        self.calls = 0

    def transform(self, chunks: list[Chunk], trace=None) -> list[Chunk]:
        self.calls += 1
        return [
            Chunk(
                id=chunk.id,
                text=f"{chunk.text} transformed",
                metadata={**chunk.metadata, "transformed": True},
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                source_ref=chunk.source_ref,
            )
            for chunk in chunks
        ]


class FakeBatchProcessor:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def process(self, chunks: list[Chunk], trace=None) -> list[ChunkRecord]:
        self.calls.append([chunk.id for chunk in chunks])
        return [
            ChunkRecord(
                id=chunk.id,
                text=chunk.text,
                metadata=chunk.metadata,
                dense_vector=[1.0, float(index)],
                sparse_vector={term: 1.0 for term in chunk.text.split()},
            )
            for index, chunk in enumerate(chunks)
        ]


class FakeVectorUpserter:
    def __init__(self) -> None:
        self.records: list[ChunkRecord] = []

    def upsert(self, records: list[ChunkRecord], trace=None) -> list[str]:
        self.records = records
        return [record.id for record in records]


class FakeBM25Indexer:
    def __init__(self) -> None:
        self.records: list[ChunkRecord] = []

    def add(self, records: list[ChunkRecord], trace=None) -> None:
        self.records = records


class FakeImageStorage:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    def save_image(
        self,
        image_id: str,
        source,
        collection: str = "default",
        doc_hash: str | None = None,
        page_num: int | None = None,
        trace=None,
    ) -> str:
        self.saved.append(
            {
                "image_id": image_id,
                "source": str(source),
                "collection": collection,
                "doc_hash": doc_hash,
                "page_num": page_num,
            }
        )
        return str(source)


def _document(tmp_path) -> Document:
    image_path = tmp_path / "img-1.png"
    image_path.write_bytes(b"image")
    return Document(
        id="doc-1",
        text="alpha beta gamma",
        metadata={
            "source_path": str(tmp_path / "sample.pdf"),
            "doc_type": "pdf",
            "images": [
                {
                    "id": "img-1",
                    "path": str(image_path),
                    "page": 1,
                    "text_offset": 0,
                    "text_length": 14,
                    "position": {},
                }
            ],
        },
    )


def _pipeline(tmp_path, **overrides):
    components = {
        "integrity_checker": FakeIntegrityChecker(),
        "loader": FakeLoader(_document(tmp_path)),
        "chunker": FakeChunker(),
        "transforms": [FakeTransform()],
        "batch_processor": FakeBatchProcessor(),
        "vector_upserter": FakeVectorUpserter(),
        "bm25_indexer": FakeBM25Indexer(),
        "image_storage": FakeImageStorage(),
        "trace_collector": TraceCollector(),
    }
    components.update(overrides)
    return IngestionPipeline(**components), components


def test_ingestion_pipeline_runs_full_orchestration(tmp_path) -> None:
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF fake")
    pipeline, components = _pipeline(tmp_path)

    result = pipeline.run(source, collection="docs")

    assert result.skipped is False
    assert result.document_id == "doc-1"
    assert result.chunk_count == 2
    assert result.record_count == 2
    assert result.vector_ids == ["doc-1-chunk-0", "doc-1-chunk-1"]
    assert result.image_count == 1
    assert components["transforms"][0].calls == 1
    assert [record.id for record in components["vector_upserter"].records] == result.vector_ids
    assert [record.id for record in components["bm25_indexer"].records] == result.vector_ids
    assert components["image_storage"].saved[0]["collection"] == "docs"
    assert components["integrity_checker"].successes[0]["metadata"]["record_count"] == 2
    assert result.trace.stages[-1].name == "ingestion_complete"
    assert result.trace.trace_type == "ingestion"
    stages = {stage.name: stage for stage in result.trace.stages}
    for stage_name in ["load", "split", "transform", "embed", "upsert"]:
        assert stage_name in stages
        assert stages[stage_name].method
        assert stages[stage_name].elapsed_ms >= 0
    assert stages["embed"].details["chunk_count"] == 2
    assert stages["upsert"].details["record_count"] == 2
    assert components["trace_collector"].traces[-1]["trace_type"] == "ingestion"


def test_ingestion_pipeline_skips_when_integrity_says_processed(tmp_path) -> None:
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF fake")
    pipeline, components = _pipeline(
        tmp_path,
        integrity_checker=FakeIntegrityChecker(skip=True),
    )

    result = pipeline.run(source)

    assert result.skipped is True
    assert components["loader"].calls == []
    assert result.trace.stages[-1].name == "ingestion_skip"
    assert result.trace.finished_at is not None
    assert components["trace_collector"].traces[-1]["stages"][-1]["name"] == "ingestion_skip"


def test_ingestion_pipeline_force_ignores_skip(tmp_path) -> None:
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF fake")
    pipeline, components = _pipeline(
        tmp_path,
        integrity_checker=FakeIntegrityChecker(skip=True),
    )

    result = pipeline.run(source, force=True)

    assert result.skipped is False
    assert components["loader"].calls == [str(source)]


def test_ingestion_pipeline_marks_failure_with_clear_stage(tmp_path) -> None:
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"%PDF fake")
    integrity = FakeIntegrityChecker()
    pipeline, _ = _pipeline(
        tmp_path,
        integrity_checker=integrity,
        loader=FakeLoader(fail=True),
    )

    with pytest.raises(IngestionPipelineError, match="pipeline failed during load"):
        pipeline.run(source)

    assert len(integrity.failures) == 1
    assert "loader exploded" in integrity.failures[0]["error"]
    assert pipeline.trace_collector.traces[-1]["stages"][-1]["name"] == "ingestion_failed"
    assert pipeline.trace_collector.traces[-1]["trace_type"] == "ingestion"
