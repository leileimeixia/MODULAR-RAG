"""Dashboard trace reading and formatting service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.settings import load_settings
from observability.logger import DEFAULT_TRACE_FILE


class TraceService:
    """Read JSONL traces and format them for dashboard trace pages."""

    def __init__(
        self,
        trace_file: str | Path | None = None,
        settings_path: str | Path = "config/settings.yaml",
    ) -> None:
        self.trace_file = Path(trace_file) if trace_file is not None else _trace_file_from_settings(settings_path)

    def list_traces(self, trace_type: str | None = None) -> list[dict[str, Any]]:
        """Return trace summaries newest-first."""
        traces = self._read_traces()
        if trace_type is not None:
            traces = [
                trace
                for trace in traces
                if trace.get("trace_type") == trace_type
            ]
        return [_trace_summary(trace) for trace in sorted(traces, key=_trace_sort_key, reverse=True)]

    def get_trace(self, trace_id: str) -> dict[str, Any]:
        """Return one trace detail with stage rows."""
        if not isinstance(trace_id, str) or not trace_id.strip():
            raise TraceServiceError("trace_id must be a non-empty string")
        for trace in self._read_traces():
            if trace.get("trace_id") == trace_id:
                return _trace_detail(trace)
        raise TraceServiceError(f"trace not found: {trace_id}")

    def list_ingestion_traces(self) -> list[dict[str, Any]]:
        """Return ingestion trace summaries newest-first."""
        return self.list_traces(trace_type="ingestion")

    def get_ingestion_trace(self, trace_id: str) -> dict[str, Any]:
        """Return one ingestion trace detail."""
        detail = self.get_trace(trace_id)
        if detail.get("trace_type") != "ingestion":
            raise TraceServiceError(f"trace is not an ingestion trace: {trace_id}")
        return detail

    def _read_traces(self) -> list[dict[str, Any]]:
        if not self.trace_file.is_file():
            return []
        traces: list[dict[str, Any]] = []
        for line_number, line in enumerate(self.trace_file.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TraceServiceError(
                    f"invalid JSON in trace file {self.trace_file} at line {line_number}"
                ) from exc
            if isinstance(payload, dict):
                traces.append(payload)
        return traces


class TraceServiceError(ValueError):
    """Raised when trace data cannot be read or formatted."""


def _trace_file_from_settings(settings_path: str | Path) -> Path:
    try:
        settings = load_settings(settings_path)
    except Exception:  # noqa: BLE001 - dashboard should fall back to default trace path.
        return Path(DEFAULT_TRACE_FILE)
    return Path(settings.observability.trace_file)


def _trace_summary(trace: dict[str, Any]) -> dict[str, Any]:
    stages = _stage_rows(trace)
    return {
        "trace_id": str(trace.get("trace_id", "")),
        "trace_type": str(trace.get("trace_type", "")),
        "started_at": str(trace.get("started_at", "")),
        "finished_at": str(trace.get("finished_at", "")),
        "total_elapsed_ms": round(float(trace.get("total_elapsed_ms", 0.0)), 2),
        "stage_count": len(stages),
        "status": _trace_status(stages),
        "source_path": _first_stage_detail(stages, "source_path"),
        "document_id": _first_stage_detail(stages, "document_id"),
    }


def _trace_detail(trace: dict[str, Any]) -> dict[str, Any]:
    stages = _stage_rows(trace)
    return {
        **_trace_summary(trace),
        "stages": stages,
        "raw": trace,
    }


def _stage_rows(trace: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_stages = trace.get("stages", [])
    if not isinstance(raw_stages, list):
        return rows
    for index, stage in enumerate(raw_stages, start=1):
        if not isinstance(stage, dict):
            continue
        details = dict(stage.get("details", {})) if isinstance(stage.get("details", {}), dict) else {}
        rows.append(
            {
                "index": index,
                "name": str(stage.get("name", "")),
                "method": str(stage.get("method", "")),
                "elapsed_ms": round(float(stage.get("elapsed_ms", 0.0)), 2),
                "recorded_at": str(stage.get("recorded_at", "")),
                "failed": bool(details.get("failed", False)),
                "details": details,
            }
        )
    return rows


def _trace_status(stages: list[dict[str, Any]]) -> str:
    if any(stage["failed"] for stage in stages):
        return "failed"
    if any(stage["name"] == "ingestion_failed" for stage in stages):
        return "failed"
    if any(stage["name"] == "ingestion_skip" for stage in stages):
        return "skipped"
    if any(stage["name"] == "ingestion_complete" for stage in stages):
        return "completed"
    return "unknown"


def _first_stage_detail(stages: list[dict[str, Any]], key: str) -> str:
    for stage in stages:
        value = stage["details"].get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _trace_sort_key(trace: dict[str, Any]) -> str:
    return str(trace.get("started_at") or trace.get("finished_at") or "")
