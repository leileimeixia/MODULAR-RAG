"""Tests for sparse BM25 retrieval."""

from __future__ import annotations

import pytest

from core import RetrievalResult
from core.query_engine import SparseRetriever, SparseRetrieverError
from core.trace import TraceContext
from libs.vector_store import BaseVectorStore, VectorQueryResult, VectorRecord


class FakeBM25Indexer:
    def __init__(self, results: list[dict[str, float | str]]) -> None:
        self.results = results
        self.calls: list[dict[str, float | str]] = []

    def query(self, query: str, top_k: int = 5) -> list[dict[str, float | str]]:
        self.calls.append({"query": query, "top_k": top_k})
        return self.results[:top_k]


class FakeVectorStore(BaseVectorStore):
    def __init__(self, records: list[VectorRecord]) -> None:
        self.records = {record.id: record for record in records}
        self.get_by_ids_calls: list[list[str]] = []

    def upsert(self, records: list[VectorRecord], trace=None) -> None:
        for record in records:
            self.records[record.id] = record

    def query(
        self,
        vector: list[float],
        top_k: int,
        filters: dict | None = None,
        trace=None,
    ) -> list[VectorQueryResult]:
        return []

    def get_by_ids(self, ids: list[str], trace=None) -> list[VectorRecord]:
        self.get_by_ids_calls.append(ids)
        return [
            self.records[record_id]
            for record_id in ids
            if record_id in self.records
        ]


def _store() -> FakeVectorStore:
    return FakeVectorStore(
        [
            VectorRecord(
                id="chunk-a",
                text="alpha content",
                vector=[1.0],
                metadata={"source_path": "docs/a.md"},
            ),
            VectorRecord(
                id="chunk-b",
                text="beta content",
                vector=[1.0],
                metadata={"source_path": "docs/b.md"},
            ),
        ]
    )


def test_sparse_retriever_queries_bm25_and_hydrates_records_in_rank_order() -> None:
    bm25 = FakeBM25Indexer(
        [
            {"chunk_id": "chunk-b", "score": 3.5},
            {"chunk_id": "chunk-a", "score": 2.0},
        ]
    )
    store = _store()

    results = SparseRetriever(bm25_indexer=bm25, vector_store=store).retrieve(
        ["alpha", "beta"],
        top_k=2,
    )

    assert bm25.calls == [{"query": "alpha beta", "top_k": 2}]
    assert store.get_by_ids_calls == [["chunk-b", "chunk-a"]]
    assert results == [
        RetrievalResult(
            chunk_id="chunk-b",
            score=3.5,
            text="beta content",
            metadata={"source_path": "docs/b.md"},
        ),
        RetrievalResult(
            chunk_id="chunk-a",
            score=2.0,
            text="alpha content",
            metadata={"source_path": "docs/a.md"},
        ),
    ]


def test_sparse_retriever_skips_bm25_ids_missing_from_vector_store() -> None:
    bm25 = FakeBM25Indexer(
        [
            {"chunk_id": "missing", "score": 9.0},
            {"chunk_id": "chunk-a", "score": 1.0},
        ]
    )

    results = SparseRetriever(bm25_indexer=bm25, vector_store=_store()).retrieve(
        ["alpha"],
        top_k=5,
    )

    assert [result.chunk_id for result in results] == ["chunk-a"]


def test_sparse_retriever_returns_empty_when_bm25_returns_empty() -> None:
    store = _store()

    results = SparseRetriever(
        bm25_indexer=FakeBM25Indexer([]),
        vector_store=store,
    ).retrieve(["unknown"], top_k=5)

    assert results == []
    assert store.get_by_ids_calls == []


@pytest.mark.parametrize(
    ("keywords", "top_k", "message"),
    [
        ([], 1, "at least one"),
        (["alpha", ""], 1, "non-empty"),
        ("alpha", 1, "list"),
        (["alpha"], 0, "top_k"),
    ],
)
def test_sparse_retriever_rejects_invalid_input(keywords, top_k, message) -> None:
    with pytest.raises(SparseRetrieverError, match=message):
        SparseRetriever(
            bm25_indexer=FakeBM25Indexer([]),
            vector_store=_store(),
        ).retrieve(keywords, top_k=top_k)


def test_sparse_retriever_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-sparse-retrieval")
    bm25 = FakeBM25Indexer(
        [
            {"chunk_id": "missing", "score": 3.0},
            {"chunk_id": "chunk-b", "score": 2.0},
        ]
    )

    results = SparseRetriever(bm25_indexer=bm25, vector_store=_store()).retrieve(
        ["beta"],
        top_k=2,
        trace=trace,
    )

    assert [result.chunk_id for result in results] == ["chunk-b"]
    assert trace.stages[-1].name == "sparse_retrieval"
    assert trace.stages[-1].method == "FakeBM25Indexer"
    assert trace.stages[-1].details == {
        "top_k": 2,
        "keyword_count": 1,
        "candidate_count": 2,
        "result_count": 1,
        "missing_count": 1,
    }
