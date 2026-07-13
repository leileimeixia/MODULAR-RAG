"""Tests for core reranker fallback orchestration."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from core import RetrievalResult
from core.query_engine import CoreReranker, CoreRerankerError
from core.trace import TraceContext
from libs.reranker import BaseReranker, RerankCandidate, RerankResult


@dataclass(frozen=True)
class FakeRerankSettings:
    top_k: int = 2


@dataclass(frozen=True)
class FakeSettings:
    rerank: FakeRerankSettings


class FakeBackend(BaseReranker):
    def __init__(
        self,
        results: list[RerankResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = results or []
        self.error = error
        self.calls: list[dict] = []

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        top_k: int | None = None,
        trace=None,
    ) -> list[RerankResult]:
        self.calls.append(
            {
                "query": query,
                "candidate_ids": [candidate.id for candidate in candidates],
                "top_k": top_k,
            }
        )
        if self.error is not None:
            raise self.error
        return self.results[:top_k]


def _candidate(chunk_id: str, score: float = 1.0) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        score=score,
        text=f"{chunk_id} text",
        metadata={"source_path": f"docs/{chunk_id}.md"},
    )


def test_core_reranker_adapts_candidates_and_returns_reranked_results() -> None:
    backend = FakeBackend(
        [
            RerankResult(
                id="b",
                text="b text",
                score=0.95,
                metadata={"source_path": "docs/b.md"},
            ),
            RerankResult(
                id="a",
                text="a text",
                score=0.5,
                metadata={"source_path": "docs/a.md"},
            ),
        ]
    )

    results = CoreReranker(backend=backend).rerank(
        "  alpha  ",
        [_candidate("a"), _candidate("b")],
        top_k=2,
    )

    assert backend.calls == [
        {"query": "alpha", "candidate_ids": ["a", "b"], "top_k": 2}
    ]
    assert results == [
        RetrievalResult(
            chunk_id="b",
            text="b text",
            score=0.95,
            metadata={"source_path": "docs/b.md"},
        ),
        RetrievalResult(
            chunk_id="a",
            text="a text",
            score=0.5,
            metadata={"source_path": "docs/a.md"},
        ),
    ]


def test_core_reranker_falls_back_to_original_order_when_backend_fails() -> None:
    candidates = [_candidate("a", 0.8), _candidate("b", 0.7), _candidate("c", 0.6)]
    backend = FakeBackend(error=TimeoutError("reranker timed out"))

    results = CoreReranker(backend=backend).rerank("alpha", candidates, top_k=2)

    assert results == candidates[:2]


def test_core_reranker_uses_settings_top_k_when_not_provided() -> None:
    backend = FakeBackend(
        [
            RerankResult(id="b", text="b text", score=1.0),
            RerankResult(id="a", text="a text", score=0.5),
        ]
    )

    results = CoreReranker(
        settings=FakeSettings(rerank=FakeRerankSettings(top_k=1)),
        backend=backend,
    ).rerank("alpha", [_candidate("a"), _candidate("b")])

    assert backend.calls[0]["top_k"] == 1
    assert [result.chunk_id for result in results] == ["b"]


def test_core_reranker_returns_empty_for_empty_candidates() -> None:
    backend = FakeBackend()

    results = CoreReranker(backend=backend).rerank("alpha", [], top_k=5)

    assert results == []
    assert backend.calls == []


@pytest.mark.parametrize(
    ("query", "candidates", "top_k", "message"),
    [
        ("", [], 1, "query"),
        ("alpha", "bad", 1, "candidates"),
        ("alpha", ["bad"], 1, "RetrievalResult"),
        ("alpha", [], -1, "top_k"),
    ],
)
def test_core_reranker_rejects_invalid_inputs(query, candidates, top_k, message) -> None:
    with pytest.raises(CoreRerankerError, match=message):
        CoreReranker(backend=FakeBackend()).rerank(query, candidates, top_k=top_k)


def test_core_reranker_records_success_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-rerank-success")
    backend = FakeBackend([RerankResult(id="a", text="a text", score=1.0)])

    CoreReranker(backend=backend).rerank("alpha", [_candidate("a")], top_k=1, trace=trace)

    assert trace.stages[-1].name == "rerank"
    assert trace.stages[-1].method == "CoreReranker"
    assert trace.stages[-1].details == {
        "top_k": 1,
        "candidate_count": 1,
        "result_count": 1,
        "fallback": False,
        "backend": "FakeBackend",
    }


def test_core_reranker_records_fallback_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-rerank-fallback")

    results = CoreReranker(
        backend=FakeBackend(error=RuntimeError("boom"))
    ).rerank("alpha", [_candidate("a")], top_k=1, trace=trace)

    assert [result.chunk_id for result in results] == ["a"]
    assert trace.stages[-1].details == {
        "top_k": 1,
        "candidate_count": 1,
        "result_count": 1,
        "fallback": True,
        "backend": "FakeBackend",
        "error": "RuntimeError",
    }
