"""Tests for batch embedding orchestration."""

from __future__ import annotations

import pytest

from core import Chunk, ChunkRecord
from core.trace import TraceContext
from ingestion.embedding import BatchProcessor, BatchProcessorError


class FakeDenseEncoder:
    def __init__(self, override_records: list[ChunkRecord] | None = None) -> None:
        self.override_records = override_records
        self.batch_sizes: list[int] = []

    def encode(self, chunks: list[Chunk], trace=None) -> list[ChunkRecord]:
        self.batch_sizes.append(len(chunks))
        if self.override_records is not None:
            return self.override_records
        return [
            ChunkRecord(
                id=chunk.id,
                text=chunk.text,
                metadata=chunk.metadata,
                dense_vector=[float(index), float(len(chunk.text))],
            )
            for index, chunk in enumerate(chunks)
        ]


class FakeSparseEncoder:
    def __init__(self, override_records: list[ChunkRecord] | None = None) -> None:
        self.override_records = override_records
        self.batch_sizes: list[int] = []

    def encode(self, chunks: list[Chunk], trace=None) -> list[ChunkRecord]:
        self.batch_sizes.append(len(chunks))
        if self.override_records is not None:
            return self.override_records
        return [
            ChunkRecord(
                id=chunk.id,
                text=chunk.text,
                metadata=chunk.metadata,
                sparse_vector={chunk.text: 1.0} if chunk.text else {},
            )
            for chunk in chunks
        ]


def _chunk(index: int, text: str | None = None) -> Chunk:
    text = text if text is not None else f"chunk {index}"
    return Chunk(
        id=f"chunk-{index}",
        text=text,
        metadata={"source_path": "docs/sample.md", "chunk_index": index},
        start_offset=index * 10,
        end_offset=index * 10 + len(text),
        source_ref="doc-1",
    )


def test_batch_processor_splits_five_chunks_into_three_stable_batches() -> None:
    chunks = [_chunk(index) for index in range(5)]
    dense_encoder = FakeDenseEncoder()
    sparse_encoder = FakeSparseEncoder()

    records = BatchProcessor(
        batch_size=2,
        dense_encoder=dense_encoder,
        sparse_encoder=sparse_encoder,
    ).process(chunks)

    assert dense_encoder.batch_sizes == [2, 2, 1]
    assert sparse_encoder.batch_sizes == [2, 2, 1]
    assert [record.id for record in records] == [f"chunk-{index}" for index in range(5)]


def test_batch_processor_combines_dense_and_sparse_vectors() -> None:
    records = BatchProcessor(
        batch_size=2,
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
    ).process([_chunk(0, "alpha")])

    assert records[0].dense_vector == [0.0, 5.0]
    assert records[0].sparse_vector == {"alpha": 1.0}
    assert records[0].text == "alpha"
    assert records[0].metadata["chunk_index"] == 0


def test_batch_processor_returns_empty_for_empty_input() -> None:
    assert BatchProcessor(dense_encoder=FakeDenseEncoder(), sparse_encoder=FakeSparseEncoder()).process([]) == []


def test_batch_processor_rejects_invalid_batch_size() -> None:
    with pytest.raises(BatchProcessorError, match="batch_size"):
        BatchProcessor(batch_size=0, dense_encoder=FakeDenseEncoder(), sparse_encoder=FakeSparseEncoder())


def test_batch_processor_rejects_non_chunk_inputs() -> None:
    with pytest.raises(BatchProcessorError, match="Chunk"):
        BatchProcessor(dense_encoder=FakeDenseEncoder(), sparse_encoder=FakeSparseEncoder()).process(["bad"])


def test_batch_processor_rejects_dense_count_mismatch() -> None:
    chunk = _chunk(0)
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(override_records=[]),
        sparse_encoder=FakeSparseEncoder(),
    )

    with pytest.raises(BatchProcessorError, match="dense encoder returned 0 records"):
        processor.process([chunk])


def test_batch_processor_rejects_sparse_count_mismatch() -> None:
    chunk = _chunk(0)
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(override_records=[]),
    )

    with pytest.raises(BatchProcessorError, match="sparse encoder returned 0 records"):
        processor.process([chunk])


def test_batch_processor_rejects_reordered_encoder_records() -> None:
    chunk = _chunk(0)
    wrong_record = ChunkRecord(
        id="other",
        text=chunk.text,
        metadata=chunk.metadata,
        dense_vector=[1.0],
    )
    processor = BatchProcessor(
        dense_encoder=FakeDenseEncoder(override_records=[wrong_record]),
        sparse_encoder=FakeSparseEncoder(),
    )

    with pytest.raises(BatchProcessorError, match="ids and order"):
        processor.process([chunk])


def test_batch_processor_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-batch")

    BatchProcessor(
        batch_size=2,
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
    ).process([_chunk(index) for index in range(3)], trace=trace)

    stage = trace.stages[-1]
    assert stage.name == "batch_processing"
    assert stage.method == "dense_sparse"
    assert stage.details["chunk_count"] == 3
    assert stage.details["batch_size"] == 2
    assert stage.details["batch_count"] == 2
    assert [batch["chunk_count"] for batch in stage.details["batches"]] == [2, 1]
