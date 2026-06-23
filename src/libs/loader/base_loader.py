"""Base contract for document loaders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from core import Document


class LoaderError(ValueError):
    """Raised when a source document cannot be loaded."""


class BaseLoader(ABC):
    """Contract for loading a source file into a Document."""

    @abstractmethod
    def load(self, path: str | Path) -> Document:
        """Load a source file into the shared Document contract."""
