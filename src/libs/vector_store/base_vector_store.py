"""Base abstractions for vector stores."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


Vector = list[float]
Metadata = dict[str, Any]


@dataclass(frozen=True)
class VectorRecord:
    """A normalized record to be stored in a vector backend."""

    id: str
    text: str
    vector: Vector
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True)
class VectorQueryResult:
    """A normalized query result returned from vector backends."""

    id: str
    text: str
    score: float
    metadata: Metadata = field(default_factory=dict)


class BaseVectorStore(ABC):
    """Common interface for vector database adapters."""

    @abstractmethod
    def upsert(
        self,
        records: list[VectorRecord],
        trace: Any | None = None,
    ) -> None:
        """Insert or replace records by id."""

    @abstractmethod
    def query(
        self,
        vector: Vector,
        top_k: int,
        filters: Metadata | None = None,
        trace: Any | None = None,
    ) -> list[VectorQueryResult]:
        """Return the top matching records for a query vector."""

    @abstractmethod
    def get_by_ids(
        self,
        ids: list[str],
        trace: Any | None = None,
    ) -> list[VectorRecord]:
        """Return stored records matching ids, preserving requested id order."""
