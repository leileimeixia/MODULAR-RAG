"""Trace collection helpers."""

from __future__ import annotations

from .trace_context import TraceContext


class TraceCollector:
    """Collect completed trace payloads for later persistence."""

    def __init__(self) -> None:
        self.traces: list[dict] = []

    def collect(self, trace: TraceContext) -> None:
        """Finish a trace and store its serialized payload."""
        if not isinstance(trace, TraceContext):
            raise TraceCollectorError("collect expects a TraceContext")
        trace.finish()
        self.traces.append(trace.to_dict())


class TraceCollectorError(ValueError):
    """Raised when trace collection inputs are invalid."""
