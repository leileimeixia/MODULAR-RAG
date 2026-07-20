"""Trace collection helpers."""

from __future__ import annotations

from pathlib import Path

from observability.logger import write_trace

from .trace_context import TraceContext


class TraceCollector:
    """Collect completed trace payloads for later persistence."""

    def __init__(
        self,
        trace_file: str | Path | None = None,
        persist: bool = False,
    ) -> None:
        self.trace_file = trace_file
        self.persist = persist
        self.traces: list[dict] = []

    def collect(self, trace: TraceContext) -> None:
        """Finish a trace and store its serialized payload."""
        if not isinstance(trace, TraceContext):
            raise TraceCollectorError("collect expects a TraceContext")
        trace.finish()
        payload = trace.to_dict()
        self.traces.append(payload)
        if self.persist:
            write_trace(payload, log_file=self.trace_file or "logs/traces.jsonl")


class TraceCollectorError(ValueError):
    """Raised when trace collection inputs are invalid."""


