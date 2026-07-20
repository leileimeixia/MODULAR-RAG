"""Structured logging helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


DEFAULT_TRACE_FILE = "logs/traces.jsonl"


def get_logger(name: str = "modular_rag") -> logging.Logger:
    """Return a stderr logger suitable for early bootstrap stages."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


class JSONFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Return a JSON string for a logging record."""
        if isinstance(record.msg, dict):
            payload = dict(record.msg)
        else:
            payload = {
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def get_trace_logger(
    log_file: str | Path = DEFAULT_TRACE_FILE,
    name: str = "modular_rag.trace",
) -> logging.Logger:
    """Return a logger configured for JSON Lines trace output."""
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    resolved = str(path.resolve())
    if not any(getattr(handler, "_trace_log_file", None) == resolved for handler in logger.handlers):
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(JSONFormatter())
        handler._trace_log_file = resolved  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def write_trace(
    trace_dict: dict[str, Any],
    log_file: str | Path = DEFAULT_TRACE_FILE,
) -> None:
    """Append one trace dictionary to a JSON Lines file."""
    if not isinstance(trace_dict, dict):
        raise LoggerError("write_trace expects a dictionary")
    logger = get_trace_logger(log_file=log_file)
    logger.info(trace_dict)
    for handler in logger.handlers:
        if getattr(handler, "_trace_log_file", None) == str(Path(log_file).resolve()):
            handler.flush()


class LoggerError(ValueError):
    """Raised when structured logging inputs are invalid."""
