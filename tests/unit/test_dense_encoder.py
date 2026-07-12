"""Tests for dense chunk encoding."""

from __future__ import annotations

import pytest

from core import Chunk
from core.trace import TraceContext
from ingestion.embedding import DenseEncoder, DenseEncoderError
from libs.embedding import BaseEmbedding


class FakeEmbedding(BaseEmbedding):
    def __init__(self, vectors: list[list[float]] | None = None) -> None:
        self.vectors = vectors
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str], trace=None) -> list[list[float]]:
        self.calls.append(texts)
        if self.vectors is not None:
            return self.vectors
        return [[float(len(text)), float(index)] for index, text in enumerate(texts)]


def _chunk(index: int, text: str) -> Chunk:
    return Chunk(
        id=f"chunk-{index}",
        text=text,
        metadata={"source_path": "docs/sample.md", "chunk_index": index},
        start_offset=index * 10,
        end_offset=index * 10 + len(text),
        source_ref="doc-1",
    )


def test_dense_encoder_embeds_chunks_in_order() -> None:
    chunks = [_chunk(0, "alpha"), _chunk(1, "beta")]
    embedding = FakeEmbedding()

    records = DenseEncoder(embedding=embedding).encode(chunks)

    assert embedding.calls == [["alpha", "beta"]]
    assert [record.id for record in records] == ["chunk-0", "chunk-1"]
    assert records[0].dense_vector == [5.0, 0.0]
    assert records[1].dense_vector == [4.0, 1.0]


def test_dense_encoder_preserves_text_and_metadata() -> None:
    chunk = _chunk(0, "alpha")

    record = DenseEncoder(embedding=FakeEmbedding()).encode([chunk])[0]

    assert record.text == chunk.text
    assert record.metadata == chunk.metadata


def test_dense_encoder_returns_empty_for_empty_input() -> None:
    assert DenseEncoder(embedding=FakeEmbedding()).encode([]) == []


def test_dense_encoder_rejects_non_chunk_inputs() -> None:
    with pytest.raises(DenseEncoderError, match="Chunk"):
        DenseEncoder(embedding=FakeEmbedding()).encode(["not chunk"])


def test_dense_encoder_rejects_vector_count_mismatch() -> None:
    chunks = [_chunk(0, "alpha"), _chunk(1, "beta")]
    encoder = DenseEncoder(embedding=FakeEmbedding(vectors=[[1.0, 2.0]]))

    with pytest.raises(DenseEncoderError, match="1 vectors for 2 chunks"):
        encoder.encode(chunks)


def test_dense_encoder_rejects_inconsistent_dimensions() -> None:
    chunks = [_chunk(0, "alpha"), _chunk(1, "beta")]
    encoder = DenseEncoder(embedding=FakeEmbedding(vectors=[[1.0, 2.0], [3.0]]))

    with pytest.raises(DenseEncoderError, match="inconsistent"):
        encoder.encode(chunks)


def test_dense_encoder_rejects_non_numeric_vectors() -> None:
    encoder = DenseEncoder(embedding=FakeEmbedding(vectors=[[1.0, "bad"]]))

    with pytest.raises(DenseEncoderError, match="non-numeric"):
        encoder.encode([_chunk(0, "alpha")])


def test_dense_encoder_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-dense")

    records = DenseEncoder(embedding=FakeEmbedding()).encode([_chunk(0, "alpha")], trace=trace)

    assert records[0].dense_vector == [5.0, 0.0]
    assert trace.stages[-1].name == "dense_encoding"
    assert trace.stages[-1].details == {"chunk_count": 1, "dimensions": 2}
