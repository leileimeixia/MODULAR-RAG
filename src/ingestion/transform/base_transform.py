"""Base contract for ingestion transforms."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core import Chunk


class TransformError(ValueError):
    """Raised when an ingestion transform cannot process chunks."""


class BaseTransform(ABC):
    """Contract for transforms that rewrite or enrich chunks."""

    @abstractmethod
    def transform(self, chunks: list[Chunk], trace: Any | None = None) -> list[Chunk]:
        """Transform chunks while preserving the Chunk contract."""
