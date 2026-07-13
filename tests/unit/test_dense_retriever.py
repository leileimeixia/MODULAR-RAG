"""Tests for dense vector retrieval."""

from __future__ import annotations

import pytest

from core import RetrievalResult
from core.query_engine import DenseRetriever, DenseRetrieverError
from core.trace import TraceContext
from libs.embedding import BaseEmbedding
from libs.vector_store import BaseVectorStore, VectorQueryResult, VectorRecord


class FakeEmbedding(BaseEmbedding):
    def __init__(self, vectors: list[list[float]] | None = None) -> None:
        self.vectors = vectors or [[1.0, 0.0]]
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str], trace=None) -> list[list[float]]:
        self.calls.append(texts)
        return self.vectors


class FakeVectorStore(BaseVectorStore):
    def __init__(self) -> None:
        self.query_calls: list[dict] = []

    def upsert(self, records: list[VectorRecord], trace=None) -> None:
        pass

    def query(
        self,
        vector: list[float],
        top_k: int,
        filters: dict | None = None,
        trace=None,
    ) -> list[VectorQueryResult]:
        self.query_calls.append(
            {"vector": vector, "top_k": top_k, "filters": filters or {}}
        )
        return [
            VectorQueryResult(
                id="chunk-a",
                text="alpha content",
                score=0.9,
                metadata={"source_path": "docs/a.md", "collection": "docs"},
            ),
            VectorQueryResult(
                id="chunk-b",
                text="beta content",
                score=0.5,
                metadata={"source_path": "docs/b.md", "collection": "docs"},
            ),
        ][:top_k]


def test_dense_retriever_embeds_query_and_calls_vector_store() -> None:
    embedding = FakeEmbedding(vectors=[[0.1, 0.2]])
    store = FakeVectorStore()

    results = DenseRetriever(
        embedding_client=embedding,
        vector_store=store,
    ).retrieve("alpha query", top_k=1, filters={"collection": "docs"})

    assert embedding.calls == [["alpha query"]]
    assert store.query_calls == [
        {"vector": [0.1, 0.2], "top_k": 1, "filters": {"collection": "docs"}}
    ]
    assert results == [
        RetrievalResult(
            chunk_id="chunk-a",
            text="alpha content",
            score=0.9,
            metadata={"source_path": "docs/a.md", "collection": "docs"},
        )
    ]


def test_dense_retriever_returns_empty_when_store_returns_empty() -> None:
    class EmptyStore(FakeVectorStore):
        def query(self, vector, top_k, filters=None, trace=None):
            return []

    assert DenseRetriever(
        embedding_client=FakeEmbedding(),
        vector_store=EmptyStore(),
    ).retrieve("nothing", top_k=5) == []


def test_dense_retriever_rejects_blank_query() -> None:
    with pytest.raises(DenseRetrieverError, match="non-empty"):
        DenseRetriever(
            embedding_client=FakeEmbedding(),
            vector_store=FakeVectorStore(),
        ).retrieve(" ", top_k=1)


def test_dense_retriever_rejects_invalid_top_k() -> None:
    with pytest.raises(DenseRetrieverError, match="top_k"):
        DenseRetriever(
            embedding_client=FakeEmbedding(),
            vector_store=FakeVectorStore(),
        ).retrieve("alpha", top_k=0)


def test_dense_retriever_rejects_embedding_count_mismatch() -> None:
    with pytest.raises(DenseRetrieverError, match="2 vectors"):
        DenseRetriever(
            embedding_client=FakeEmbedding(vectors=[[1.0], [2.0]]),
            vector_store=FakeVectorStore(),
        ).retrieve("alpha", top_k=1)


def test_dense_retriever_rejects_empty_query_vector() -> None:
    with pytest.raises(DenseRetrieverError, match="empty"):
        DenseRetriever(
            embedding_client=FakeEmbedding(vectors=[[]]),
            vector_store=FakeVectorStore(),
        ).retrieve("alpha", top_k=1)


def test_dense_retriever_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-dense-retrieval")

    results = DenseRetriever(
        embedding_client=FakeEmbedding(),
        vector_store=FakeVectorStore(),
    ).retrieve("alpha", top_k=2, filters={"collection": "docs"}, trace=trace)

    assert len(results) == 2
    assert trace.stages[-1].name == "dense_retrieval"
    assert trace.stages[-1].method == "FakeVectorStore"
    assert trace.stages[-1].details == {
        "top_k": 2,
        "result_count": 2,
        "filters": {"collection": "docs"},
    }
