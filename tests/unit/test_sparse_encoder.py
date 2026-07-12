"""Tests for sparse chunk encoding."""

from __future__ import annotations

import pytest

from core import Chunk
from core.trace import TraceContext
from ingestion.embedding import SparseEncoder, SparseEncoderError


def _chunk(index: int, text: str) -> Chunk:
    return Chunk(
        id=f"chunk-{index}",
        text=text,
        metadata={"source_path": "docs/sample.md", "chunk_index": index},
        start_offset=index * 10,
        end_offset=index * 10 + len(text),
        source_ref="doc-1",
    )


def test_sparse_encoder_counts_terms_case_insensitively() -> None:
    records = SparseEncoder().encode([_chunk(0, "Alpha beta alpha, BETA!")])

    assert records[0].sparse_vector == {"alpha": 2.0, "beta": 2.0}


def test_sparse_encoder_preserves_order_text_and_metadata() -> None:
    chunks = [_chunk(0, "first chunk"), _chunk(1, "second chunk")]

    records = SparseEncoder().encode(chunks)

    assert [record.id for record in records] == ["chunk-0", "chunk-1"]
    assert records[0].text == chunks[0].text
    assert records[0].metadata == chunks[0].metadata


def test_sparse_encoder_returns_empty_for_empty_input() -> None:
    assert SparseEncoder().encode([]) == []


def test_sparse_encoder_marks_empty_text_with_empty_sparse_vector() -> None:
    records = SparseEncoder().encode([_chunk(0, "")])

    assert records[0].sparse_vector == {}


def test_sparse_encoder_rejects_non_chunk_inputs() -> None:
    with pytest.raises(SparseEncoderError, match="Chunk"):
        SparseEncoder().encode(["not chunk"])


def test_sparse_encoder_tokenizes_unicode_words() -> None:
    records = SparseEncoder().encode([_chunk(0, "RAG 检索 RAG")])

    assert records[0].sparse_vector == {"rag": 2.0, "检索": 1.0}


def test_sparse_encoder_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-sparse")

    records = SparseEncoder().encode(
        [_chunk(0, "alpha alpha"), _chunk(1, "")],
        trace=trace,
    )

    assert records[0].sparse_vector == {"alpha": 2.0}
    assert trace.stages[-1].name == "sparse_encoding"
    assert trace.stages[-1].method == "term_frequency"
    assert trace.stages[-1].details == {
        "chunk_count": 2,
        "total_terms": 2,
        "empty_chunks": 1,
    }
