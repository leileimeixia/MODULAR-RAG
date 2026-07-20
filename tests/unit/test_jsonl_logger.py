"""Tests for JSON Lines trace logging."""

from __future__ import annotations

import json
import logging

import pytest

from core.trace import TraceCollector, TraceContext
from observability.logger import JSONFormatter, LoggerError, get_trace_logger, write_trace


def test_json_formatter_formats_dict_message_as_json() -> None:
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg={"trace_id": "trace-1", "trace_type": "query"},
        args=(),
        exc_info=None,
    )

    assert json.loads(formatter.format(record)) == {
        "trace_id": "trace-1",
        "trace_type": "query",
    }


def test_write_trace_appends_one_json_line(tmp_path) -> None:
    trace_file = tmp_path / "logs" / "traces.jsonl"
    trace = {
        "trace_id": "trace-1",
        "trace_type": "query",
        "started_at": "2026-07-16T00:00:00+00:00",
        "finished_at": "2026-07-16T00:00:01+00:00",
        "total_elapsed_ms": 1000.0,
        "stages": [],
    }

    write_trace(trace, log_file=trace_file)

    lines = trace_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == trace


def test_get_trace_logger_does_not_duplicate_handlers_for_same_file(tmp_path) -> None:
    trace_file = tmp_path / "traces.jsonl"
    logger = get_trace_logger(log_file=trace_file, name="test.trace.no_duplicate")
    get_trace_logger(log_file=trace_file, name="test.trace.no_duplicate")

    matching_handlers = [
        handler
        for handler in logger.handlers
        if getattr(handler, "_trace_log_file", None) == str(trace_file.resolve())
    ]
    assert len(matching_handlers) == 1


def test_trace_collector_can_persist_trace_to_jsonl(tmp_path) -> None:
    trace_file = tmp_path / "traces.jsonl"
    collector = TraceCollector(trace_file=trace_file, persist=True)
    trace = TraceContext(trace_id="trace-persist", trace_type="ingestion")
    trace.record_stage("load", method="PdfLoader", elapsed_ms=2.5)

    collector.collect(trace)

    payload = json.loads(trace_file.read_text(encoding="utf-8").splitlines()[0])
    assert payload["trace_id"] == "trace-persist"
    assert payload["trace_type"] == "ingestion"
    assert payload["stages"][0]["elapsed_ms"] == 2.5


def test_write_trace_rejects_non_dict_payload(tmp_path) -> None:
    with pytest.raises(LoggerError, match="dictionary"):
        write_trace(["not", "dict"], log_file=tmp_path / "traces.jsonl")  # type: ignore[arg-type]
