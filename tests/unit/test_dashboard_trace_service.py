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
