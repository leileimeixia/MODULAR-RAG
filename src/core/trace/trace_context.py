"""Minimal trace context used before the full observability phase."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass
class TraceStage:
    """One recorded trace stage."""

    name: str
    method: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class TraceContext:
    """Small trace context with stage recording; F1 will enrich it later."""

    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or str(uuid4())
        self.stages: list[TraceStage] = []

    def record_stage(
        self,
        name: str,
        method: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Append one stage record."""
        self.stages.append(
            TraceStage(name=name, method=method, details=dict(details or {}))
        )
