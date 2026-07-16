"""Trace context for request-level observability."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


VALID_TRACE_TYPES = {"query", "ingestion"}


@dataclass
class TraceStage:
    """One recorded trace stage."""

    name: str
    method: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the stage to a JSON-compatible dictionary."""
        return {
            "name": self.name,
            "method": self.method,
            "details": dict(self.details),
            "recorded_at": self.recorded_at,
            "elapsed_ms": float(self.elapsed_ms),
        }


class TraceContext:
    """Request-scoped trace context with stage recording and timing."""

    def __init__(
        self,
        trace_id: str | None = None,
        trace_type: str = "query",
    ) -> None:
        if trace_type not in VALID_TRACE_TYPES:
            raise TraceContextError(
                "trace_type must be either 'query' or 'ingestion'"
            )
        self.trace_id = trace_id or str(uuid4())
        self.trace_type = trace_type
        self.started_at = datetime.now(UTC).isoformat()
        self.finished_at: str | None = None
        self._started_monotonic = time.perf_counter()
        self._finished_monotonic: float | None = None
        self.stages: list[TraceStage] = []

    def record_stage(
        self,
        name: str,
        method: str = "",
        details: dict[str, Any] | None = None,
        elapsed_ms: float | None = None,
    ) -> None:
        """Append one stage record."""
        if not isinstance(name, str) or not name:
            raise TraceContextError("stage name must be a non-empty string")
        if elapsed_ms is not None and elapsed_ms < 0:
            raise TraceContextError("elapsed_ms must be greater than or equal to 0")
        self.stages.append(
            TraceStage(
                name=name,
                method=method,
                details=dict(details or {}),
                elapsed_ms=float(elapsed_ms or 0.0),
            )
        )

    def finish(self) -> None:
        """Mark this trace as finished."""
        if self.finished_at is None:
            self.finished_at = datetime.now(UTC).isoformat()
            self._finished_monotonic = time.perf_counter()

    def elapsed_ms(self, stage_name: str | None = None) -> float:
        """Return total elapsed milliseconds or a recorded stage duration."""
        if stage_name is not None:
            for stage in self.stages:
                if stage.name == stage_name:
                    return float(stage.elapsed_ms)
            raise TraceContextError(f"trace stage not found: {stage_name}")

        end = self._finished_monotonic or time.perf_counter()
        return max(0.0, (end - self._started_monotonic) * 1000)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this trace to a JSON-compatible dictionary."""
        return {
            "trace_id": self.trace_id,
            "trace_type": self.trace_type,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_elapsed_ms": self.elapsed_ms(),
            "stages": [stage.to_dict() for stage in self.stages],
        }


class TraceContextError(ValueError):
    """Raised when trace context inputs are invalid."""
