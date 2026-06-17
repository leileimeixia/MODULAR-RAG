"""Base abstractions for text splitters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SplitResult:
    """Normalized result returned by splitter implementations."""

    chunks: list[str]


class BaseSplitter(ABC):
    """Common interface for all text splitting strategies."""

    @abstractmethod
    def split_text(self, text: str, trace: Any | None = None) -> list[str]:
        """Split text into ordered chunks."""
