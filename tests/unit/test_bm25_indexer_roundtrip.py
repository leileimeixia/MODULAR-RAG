"""Round-trip tests for the persistent BM25 indexer."""

from __future__ import annotations

import math

import pytest

from core import ChunkRecord
from core.trace import TraceContext
from ingestion.storage import BM25Indexer, BM25IndexerError


def _record(chunk_id: str, sparse_vector: dict[str, float]) -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id,
        text=f"text for {chunk_id}",
        metadata={"source_path": "docs/sample.md"},
        sparse_vector=sparse_vector,
    )


def test_bm25_indexer_build_load_and_query_roundtrip(tmp_path) -> None:
    indexer = BM25Indexer(index_dir=tmp_path)
    indexer.build(
        [
            _record("chunk-a", {"alpha": 3.0, "shared": 1.0}),
            _record("chunk-b", {"beta": 2.0, "shared": 1.0}),
            _record("chunk-c", {"gamma": 1.0}),
        ]
    )

    loaded = BM25Indexer(index_dir=tmp_path).load()
    results = loaded.query("alpha", top_k=3)

    assert (tmp_path / "bm25_index.pkl").is_file()
    assert [result["chunk_id"] for result in results] == ["chunk-a"]
    assert results[0]["score"] > 0


def test_bm25_indexer_calculates_idf_with_expected_formula(tmp_path) -> None:
    indexer = BM25Indexer(index_dir=tmp_path)

    indexer.build(
        [
            _record("chunk-a", {"rare": 1.0, "common": 1.0}),
            _record("chunk-b", {"common": 1.0}),
            _record("chunk-c", {"other": 1.0}),
        ]
    )

    assert indexer.index["rare"]["idf"] == pytest.approx(math.log((3 - 1 + 0.5) / (1 + 0.5)))
    assert indexer.index["common"]["idf"] == pytest.approx(math.log((3 - 2 + 0.5) / (2 + 0.5)))


def test_bm25_indexer_stores_postings_with_tf_and_doc_length(tmp_path) -> None:
    indexer = BM25Indexer(index_dir=tmp_path)

    indexer.build([_record("chunk-a", {"alpha": 2.0, "beta": 1.0})])

    assert indexer.index["alpha"]["postings"] == [
        {"chunk_id": "chunk-a", "tf": 2.0, "doc_length": 3.0}
    ]


def test_bm25_indexer_build_replaces_existing_index(tmp_path) -> None:
    indexer = BM25Indexer(index_dir=tmp_path)
    indexer.build([_record("chunk-a", {"alpha": 1.0})])

    indexer.build([_record("chunk-b", {"beta": 1.0})])

    assert "alpha" not in indexer.index
    assert [result["chunk_id"] for result in indexer.query("beta")] == ["chunk-b"]


def test_bm25_indexer_add_replaces_records_incrementally(tmp_path) -> None:
    indexer = BM25Indexer(index_dir=tmp_path)
    indexer.build([_record("chunk-a", {"alpha": 1.0})])

    indexer.add([_record("chunk-b", {"beta": 1.0}), _record("chunk-a", {"gamma": 1.0})])

    assert "alpha" not in indexer.index
    assert [result["chunk_id"] for result in indexer.query("beta")] == ["chunk-b"]
    assert [result["chunk_id"] for result in indexer.query("gamma")] == ["chunk-a"]


def test_bm25_indexer_remove_document_rebuilds_index(tmp_path) -> None:
    indexer = BM25Indexer(index_dir=tmp_path)
    indexer.build(
        [
            _record("chunk-a", {"alpha": 1.0}),
            ChunkRecord(
                id="chunk-b",
                text="beta",
                metadata={"source_path": "docs/other.md"},
                sparse_vector={"beta": 1.0},
            ),
        ]
    )

    removed = indexer.remove_document(source_path="docs/sample.md")

    assert removed == 1
    assert indexer.query("alpha") == []
    assert [result["chunk_id"] for result in indexer.query("beta")] == ["chunk-b"]


def test_bm25_indexer_handles_empty_sparse_vectors(tmp_path) -> None:
    indexer = BM25Indexer(index_dir=tmp_path)

    indexer.build([_record("chunk-empty", {}), _record("chunk-a", {"alpha": 1.0})])

    assert indexer.doc_count == 2
    assert indexer.query("missing") == []


def test_bm25_indexer_rejects_records_without_sparse_vector(tmp_path) -> None:
    record = ChunkRecord(
        id="chunk-a",
        text="alpha",
        metadata={"source_path": "docs/sample.md"},
    )

    with pytest.raises(BM25IndexerError, match="sparse_vector"):
        BM25Indexer(index_dir=tmp_path).build([record])


def test_bm25_indexer_records_trace_stage(tmp_path) -> None:
    trace = TraceContext(trace_id="trace-bm25")

    BM25Indexer(index_dir=tmp_path).build([_record("chunk-a", {"alpha": 1.0})], trace=trace)

    assert trace.stages[-1].name == "bm25_build"
    assert trace.stages[-1].method == "pickle"
    assert trace.stages[-1].details["doc_count"] == 1
    assert trace.stages[-1].details["term_count"] == 1
