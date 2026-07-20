"""Integration-style tests for hybrid retrieval orchestration."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from core import RetrievalResult
from core.query_engine import HybridSearch, HybridSearchError, ProcessedQuery
from core.trace import TraceContext


@dataclass(frozen=True)
class FakeRetrievalSettings:
    dense_top_k: int = 3
    sparse_top_k: int = 4
    fusion_top_k: int = 5
    rrf_k: int = 60


@dataclass(frozen=True)
class FakeSettings:
    retrieval: FakeRetrievalSettings


class FakeQueryProcessor:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def process(self, query: str, filters=None, trace=None) -> ProcessedQuery:
        self.calls.append({"query": query, "filters": filters or {}})
        return ProcessedQuery(
            query=query.strip(),
            keywords=["alpha", "beta"],
            filters={"collection": "docs", **(filters or {})},
        )


class FakeDenseRetriever:
    def __init__(
        self,
        results: list[RetrievalResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.error = error
        self.calls: list[dict] = []

    def retrieve(self, query: str, top_k: int, filters=None, trace=None):
        self.calls.append({"query": query, "top_k": top_k, "filters": filters or {}})
        if self.error is not None:
            raise self.error
        return self.results[:top_k]


class FakeSparseRetriever:
    def __init__(
        self,
        results: list[RetrievalResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.error = error
        self.calls: list[dict] = []

    def retrieve(self, keywords: list[str], top_k: int, trace=None):
        self.calls.append({"keywords": keywords, "top_k": top_k})
        if self.error is not None:
            raise self.error
        return self.results[:top_k]


class FakeFusion:
    def __init__(self, results: list[RetrievalResult] | None = None) -> None:
        self.results = results
        self.calls: list[dict] = []

    def fuse(self, dense_results, sparse_results, top_k: int, trace=None):
        self.calls.append(
            {
                "dense_ids": [result.chunk_id for result in dense_results],
                "sparse_ids": [result.chunk_id for result in sparse_results],
                "top_k": top_k,
            }
        )
        if self.results is not None:
            return self.results[:top_k]
        return [*dense_results, *sparse_results][:top_k]


def _result(chunk_id: str, collection: str = "docs") -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        score=1.0,
        text=f"{chunk_id} text",
        metadata={
            "source_path": f"docs/{chunk_id}.md",
            "collection": collection,
            "language": "en",
        },
    )


def _search(
    dense_results: list[RetrievalResult] | None = None,
    sparse_results: list[RetrievalResult] | None = None,
    fusion_results: list[RetrievalResult] | None = None,
    dense_error: Exception | None = None,
    sparse_error: Exception | None = None,
) -> tuple[HybridSearch, FakeQueryProcessor, FakeDenseRetriever, FakeSparseRetriever, FakeFusion]:
    query_processor = FakeQueryProcessor()
    dense_retriever = FakeDenseRetriever(dense_results, dense_error)
    sparse_retriever = FakeSparseRetriever(sparse_results, sparse_error)
    fusion = FakeFusion(fusion_results)
    return (
        HybridSearch(
            settings=FakeSettings(retrieval=FakeRetrievalSettings()),
            query_processor=query_processor,
            dense_retriever=dense_retriever,
            sparse_retriever=sparse_retriever,
            fusion=fusion,
        ),
        query_processor,
        dense_retriever,
        sparse_retriever,
        fusion,
    )


def test_hybrid_search_orchestrates_query_dense_sparse_and_fusion() -> None:
    search, processor, dense, sparse, fusion = _search(
        dense_results=[_result("dense-a"), _result("dense-b")],
        sparse_results=[_result("sparse-a")],
    )

    results = search.search(" alpha beta ", top_k=2, filters={"language": "en"})

    assert processor.calls == [
        {"query": " alpha beta ", "filters": {"language": "en"}}
    ]
    assert dense.calls == [
        {
            "query": "alpha beta",
            "top_k": 3,
            "filters": {"collection": "docs", "language": "en"},
        }
    ]
    assert sparse.calls == [{"keywords": ["alpha", "beta"], "top_k": 4}]
    assert fusion.calls == [
        {
            "dense_ids": ["dense-a", "dense-b"],
            "sparse_ids": ["sparse-a"],
            "top_k": 5,
        }
    ]
    assert [result.chunk_id for result in results] == ["dense-a", "dense-b"]


def test_hybrid_search_applies_metadata_filters_after_fusion() -> None:
    search, *_ = _search(
        fusion_results=[
            _result("public-a", collection="docs"),
            _result("private-a", collection="private"),
            _result("public-b", collection="docs"),
        ]
    )

    results = search.search("alpha", top_k=5)

    assert [result.chunk_id for result in results] == ["public-a", "public-b"]


def test_hybrid_search_degrades_when_dense_route_fails() -> None:
    search, _, _, sparse, fusion = _search(
        sparse_results=[_result("sparse-a")],
        dense_error=RuntimeError("dense unavailable"),
    )

    results = search.search("alpha", top_k=3)

    assert sparse.calls == [{"keywords": ["alpha", "beta"], "top_k": 4}]
    assert fusion.calls[0]["dense_ids"] == []
    assert [result.chunk_id for result in results] == ["sparse-a"]


def test_hybrid_search_degrades_when_sparse_route_fails() -> None:
    search, _, dense, _, fusion = _search(
        dense_results=[_result("dense-a")],
        sparse_error=RuntimeError("sparse unavailable"),
    )

    results = search.search("alpha", top_k=3)

    assert dense.calls[0]["top_k"] == 3
    assert fusion.calls[0]["sparse_ids"] == []
    assert [result.chunk_id for result in results] == ["dense-a"]


def test_hybrid_search_raises_when_both_routes_fail() -> None:
    search, *_ = _search(
        dense_error=RuntimeError("dense unavailable"),
        sparse_error=RuntimeError("sparse unavailable"),
    )

    with pytest.raises(HybridSearchError, match="both dense and sparse"):
        search.search("alpha", top_k=3)


def test_hybrid_search_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-hybrid")
    search, *_ = _search(
        dense_results=[_result("dense-a")],
        sparse_results=[_result("sparse-a")],
    )

    results = search.search("alpha", top_k=2, trace=trace)

    assert [result.chunk_id for result in results] == ["dense-a", "sparse-a"]
    stages = {stage.name: stage for stage in trace.stages}
    assert list(stages) == [
        "query_processing",
        "dense_retrieval",
        "sparse_retrieval",
        "fusion",
        "hybrid_search",
    ]
    for stage in stages.values():
        assert stage.method
        assert stage.elapsed_ms >= 0
    assert stages["hybrid_search"].method == "HybridSearch"
    assert stages["hybrid_search"].details == {
        "top_k": 2,
        "dense_count": 1,
        "sparse_count": 1,
        "fusion_count": 2,
        "result_count": 2,
        "filters": {"collection": "docs"},
        "dense_failed": False,
        "sparse_failed": False,
    }
    assert trace.to_dict()["trace_type"] == "query"


def test_hybrid_search_rejects_invalid_inputs() -> None:
    search, *_ = _search()

    with pytest.raises(HybridSearchError, match="top_k"):
        search.search("alpha", top_k=0)
    with pytest.raises(HybridSearchError, match="filters"):
        search.search("alpha", top_k=1, filters="bad")
