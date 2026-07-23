"""Tests for dashboard trace service."""

from __future__ import annotations

import json

import pytest

from observability.dashboard.services.trace_service import TraceService, TraceServiceError


def test_trace_service_lists_ingestion_traces_newest_first(tmp_path) -> None:
    trace_file = tmp_path / "traces.jsonl"
    _write_jsonl(
        trace_file,
        [
            _trace("old", "ingestion", "2026-07-22T00:00:00Z", "ingestion_complete"),
            _trace("query", "query", "2026-07-22T00:01:00Z", "query_processing"),
            _trace("new", "ingestion", "2026-07-22T00:02:00Z", "ingestion_failed", failed=True),
        ],
    )

    traces = TraceService(trace_file=trace_file).list_ingestion_traces()

    assert [trace["trace_id"] for trace in traces] == ["new", "old"]
    assert traces[0]["status"] == "failed"
    assert traces[1]["status"] == "completed"
    assert traces[1]["source_path"] == "docs/sample.pdf"


def test_trace_service_returns_ingestion_trace_detail(tmp_path) -> None:
    trace_file = tmp_path / "traces.jsonl"
    _write_jsonl(
        trace_file,
        [_trace("trace-1", "ingestion", "2026-07-22T00:00:00Z", "ingestion_complete")],
    )

    detail = TraceService(trace_file=trace_file).get_ingestion_trace("trace-1")

    assert detail["trace_id"] == "trace-1"
    assert detail["stage_count"] == 2
    assert detail["stages"][0]["name"] == "load"
    assert detail["stages"][0]["elapsed_ms"] == 12.5
    assert detail["stages"][0]["details"]["source_path"] == "docs/sample.pdf"


def test_trace_service_returns_query_trace_detail(tmp_path) -> None:
    trace_file = tmp_path / "traces.jsonl"
    _write_jsonl(trace_file, [_query_trace("query-1")])

    traces = TraceService(trace_file=trace_file).list_query_traces()
    detail = TraceService(trace_file=trace_file).get_query_trace("query-1")

    assert traces[0]["trace_id"] == "query-1"
    assert detail["retrieval_comparison"] == [
        {
            "route": "Dense",
            "stage": "dense_retrieval",
            "method": "DenseRetriever",
            "elapsed_ms": 10.0,
            "result_count": 3,
            "failed": False,
        },
        {
            "route": "Sparse",
            "stage": "sparse_retrieval",
            "method": "SparseRetriever",
            "elapsed_ms": 8.0,
            "result_count": 2,
            "failed": False,
        },
        {
            "route": "Fusion",
            "stage": "fusion",
            "method": "RRFusion",
            "elapsed_ms": 1.0,
            "result_count": 4,
            "failed": False,
        },
    ]
    assert detail["rerank_summary"]["backend"] == "NoneReranker"
    assert detail["rerank_summary"]["candidate_count"] == 4


def test_trace_service_rejects_invalid_jsonl(tmp_path) -> None:
    trace_file = tmp_path / "traces.jsonl"
    trace_file.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(TraceServiceError, match="invalid JSON"):
        TraceService(trace_file=trace_file).list_ingestion_traces()


def _write_jsonl(path, payloads) -> None:
    path.write_text(
        "\n".join(json.dumps(payload, sort_keys=True) for payload in payloads),
        encoding="utf-8",
    )


def _trace(trace_id: str, trace_type: str, started_at: str, terminal_stage: str, failed: bool = False):
    return {
        "trace_id": trace_id,
        "trace_type": trace_type,
        "started_at": started_at,
        "finished_at": started_at,
        "total_elapsed_ms": 42.25,
        "stages": [
            {
                "name": "load",
                "method": "PdfLoader",
                "elapsed_ms": 12.5,
                "recorded_at": started_at,
                "details": {
                    "source_path": "docs/sample.pdf",
                    "failed": failed,
                },
            },
            {
                "name": terminal_stage,
                "method": "pipeline",
                "elapsed_ms": 1.0,
                "recorded_at": started_at,
                "details": {
                    "document_id": "doc-1",
                    "failed": failed,
                },
            },
        ],
    }


def _query_trace(trace_id: str):
    return {
        "trace_id": trace_id,
        "trace_type": "query",
        "started_at": "2026-07-23T00:00:00Z",
        "finished_at": "2026-07-23T00:00:01Z",
        "total_elapsed_ms": 25.0,
        "stages": [
            {
                "name": "dense_retrieval",
                "method": "DenseRetriever",
                "elapsed_ms": 10.0,
                "recorded_at": "2026-07-23T00:00:00Z",
                "details": {"result_count": 3, "failed": False},
            },
            {
                "name": "sparse_retrieval",
                "method": "SparseRetriever",
                "elapsed_ms": 8.0,
                "recorded_at": "2026-07-23T00:00:00Z",
                "details": {"result_count": 2, "failed": False},
            },
            {
                "name": "fusion",
                "method": "RRFusion",
                "elapsed_ms": 1.0,
                "recorded_at": "2026-07-23T00:00:00Z",
                "details": {"result_count": 4},
            },
            {
                "name": "rerank",
                "method": "CoreReranker",
                "elapsed_ms": 2.0,
                "recorded_at": "2026-07-23T00:00:00Z",
                "details": {
                    "backend": "NoneReranker",
                    "candidate_count": 4,
                    "result_count": 4,
                    "top_k": 5,
                    "fallback": False,
                },
            },
        ],
    }
