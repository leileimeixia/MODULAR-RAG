"""Base abstractions for embedding providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


Vector = list[float]


@dataclass(frozen=True)
class EmbeddingResponse:
    """Normalized embedding response returned by provider implementations."""

    vectors: list[Vector]
    raw: Any | None = None


class BaseEmbedding(ABC):
    """Common interface for all embedding providers."""

    @abstractmethod
    def embed(self, texts: list[str], trace: Any | None = None) -> list[Vector]:
        """Embed a batch of texts into dense vectors."""
