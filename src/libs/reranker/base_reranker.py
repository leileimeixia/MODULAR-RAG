"""Base abstractions for rerankers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


Metadata = dict[str, Any]


@dataclass(frozen=True)
class RerankCandidate:
    """A normalized candidate passed into reranker implementations."""

    id: str
    text: str
    score: float = 0.0
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True)
class RerankResult:
    """A normalized reranked result."""

    id: str
    text: str
    score: float
    metadata: Metadata = field(default_factory=dict)


class BaseReranker(ABC):
    """Common interface for all reranking strategies."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        top_k: int | None = None,
        trace: Any | None = None,
    ) -> list[RerankResult]:
        """Return candidates ordered by relevance to the query."""
