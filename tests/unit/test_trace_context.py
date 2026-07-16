"""Tests for trace context observability contracts."""

from __future__ import annotations

import json
import time

import pytest

from core.trace import TraceCollector, TraceContext, TraceContextError


def test_trace_context_records_stage_and_serializes_payload() -> None:
    trace = TraceContext(trace_id="trace-1", trace_type="ingestion")

    trace.record_stage(
        "load",
        method="PdfLoader",
        details={"source_path": "docs/a.pdf"},
        elapsed_ms=12.5,
    )
    trace.finish()

    payload = trace.to_dict()
    assert payload["trace_id"] == "trace-1"
    assert payload["trace_type"] == "ingestion"
    assert payload["started_at"]
    assert payload["finished_at"]
    assert payload["total_elapsed_ms"] >= 0
    assert payload["stages"] == [
        {
            "name": "load",
            "method": "PdfLoader",
            "details": {"source_path": "docs/a.pdf"},
            "recorded_at": trace.stages[0].recorded_at,
            "elapsed_ms": 12.5,
        }
    ]
    json.dumps(payload)


def test_trace_context_defaults_to_query_type_and_keeps_legacy_trace_id_arg() -> None:
    trace = TraceContext(trace_id="trace-query")

    assert trace.trace_id == "trace-query"
    assert trace.trace_type == "query"


def test_elapsed_ms_returns_total_before_and_after_finish() -> None:
    trace = TraceContext()
    time.sleep(0.001)

    before_finish = trace.elapsed_ms()
    trace.finish()
    after_finish = trace.elapsed_ms()

    assert before_finish > 0
    assert after_finish >= before_finish
    assert trace.elapsed_ms() == after_finish


def test_elapsed_ms_returns_stage_duration_by_name() -> None:
    trace = TraceContext()
    trace.record_stage("rerank", elapsed_ms=3.25)

    assert trace.elapsed_ms("rerank") == 3.25


def test_trace_context_rejects_invalid_inputs() -> None:
    with pytest.raises(TraceContextError, match="trace_type"):
        TraceContext(trace_type="other")

    trace = TraceContext()
    with pytest.raises(TraceContextError, match="stage name"):
        trace.record_stage("")
    with pytest.raises(TraceContextError, match="elapsed_ms"):
        trace.record_stage("load", elapsed_ms=-1)
    with pytest.raises(TraceContextError, match="not found"):
        trace.elapsed_ms("missing")


def test_trace_collector_finishes_and_collects_trace_payload() -> None:
    collector = TraceCollector()
    trace = TraceContext(trace_id="trace-collect", trace_type="query")
    trace.record_stage("query_processor", method="QueryProcessor")

    collector.collect(trace)

    assert trace.finished_at is not None
    assert collector.traces[0]["trace_id"] == "trace-collect"
    assert collector.traces[0]["trace_type"] == "query"
