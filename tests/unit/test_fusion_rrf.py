"""Tests for reciprocal rank fusion."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from core import RetrievalResult
from core.query_engine import RRFusion, RRFusionError
from core.trace import TraceContext


@dataclass(frozen=True)
class FakeRetrievalSettings:
    rrf_k: int


@dataclass(frozen=True)
class FakeSettings:
    retrieval: FakeRetrievalSettings


def _result(chunk_id: str, source: str, score: float = 1.0) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        score=score,
        text=f"{chunk_id} text from {source}",
        metadata={"source_path": f"docs/{source}.md", "route": source},
    )


def test_rrf_fusion_merges_dense_and_sparse_rankings_deterministically() -> None:
    dense = [_result("a", "dense"), _result("b", "dense"), _result("c", "dense")]
    sparse = [_result("c", "sparse"), _result("b", "sparse"), _result("d", "sparse")]

    results = RRFusion(rrf_k=60).fuse(dense, sparse, top_k=4)

    assert [result.chunk_id for result in results] == ["c", "b", "a", "d"]
    assert results[0].score == pytest.approx((1 / 63) + (1 / 61))
    assert results[1].score == pytest.approx((1 / 62) + (1 / 62))
    assert results[0].text == "c text from dense"
    assert results[0].metadata["route"] == "dense"


def test_rrf_fusion_respects_top_k() -> None:
    results = RRFusion(rrf_k=60).fuse(
        [_result("a", "dense"), _result("b", "dense")],
        [_result("c", "sparse")],
        top_k=2,
    )

    assert [result.chunk_id for result in results] == ["a", "c"]


def test_rrf_fusion_reads_rrf_k_from_settings() -> None:
    settings = FakeSettings(retrieval=FakeRetrievalSettings(rrf_k=10))

    results = RRFusion(settings=settings).fuse([_result("a", "dense")], [], top_k=1)

    assert results[0].score == pytest.approx(1 / 11)


def test_rrf_fusion_skips_duplicate_ids_within_same_route() -> None:
    dense = [_result("a", "dense", 0.9), _result("a", "dense", 0.1)]

    results = RRFusion(rrf_k=60).fuse(dense, [], top_k=5)

    assert [result.chunk_id for result in results] == ["a"]
    assert results[0].score == pytest.approx(1 / 61)


def test_rrf_fusion_uses_chunk_id_as_final_tie_breaker() -> None:
    results = RRFusion(rrf_k=60).fuse(
        [_result("b", "dense")],
        [_result("a", "sparse")],
        top_k=2,
    )

    assert [result.chunk_id for result in results] == ["a", "b"]


@pytest.mark.parametrize(
    ("dense", "sparse", "top_k", "message"),
    [
        ("bad", [], 1, "dense_results"),
        ([], ["bad"], 1, "sparse_results"),
        ([], [], 0, "top_k"),
    ],
)
def test_rrf_fusion_rejects_invalid_inputs(dense, sparse, top_k, message) -> None:
    with pytest.raises(RRFusionError, match=message):
        RRFusion(rrf_k=60).fuse(dense, sparse, top_k=top_k)


def test_rrf_fusion_rejects_invalid_rrf_k() -> None:
    with pytest.raises(RRFusionError, match="rrf_k"):
        RRFusion(rrf_k=0)


def test_rrf_fusion_records_trace_stage() -> None:
    trace = TraceContext(trace_id="trace-rrf-fusion")

    results = RRFusion(rrf_k=10).fuse(
        [_result("a", "dense")],
        [_result("a", "sparse"), _result("b", "sparse")],
        top_k=2,
        trace=trace,
    )

    assert [result.chunk_id for result in results] == ["a", "b"]
    assert trace.stages[-1].name == "rrf_fusion"
    assert trace.stages[-1].method == "RRFusion"
    assert trace.stages[-1].details == {
        "rrf_k": 10,
        "top_k": 2,
        "dense_count": 1,
        "sparse_count": 2,
        "result_count": 2,
    }
