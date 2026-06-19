"""Factory for pluggable vector stores."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.settings import Settings, VectorStoreSettings

from .base_vector_store import BaseVectorStore


class VectorStoreFactoryError(ValueError):
    """Raised when a vector store provider cannot be created."""


VectorStoreCreator = Callable[[VectorStoreSettings], BaseVectorStore]


class VectorStoreFactory:
    """Create vector store implementations from project settings."""

    _registry: dict[str, VectorStoreCreator] = {}

    @classmethod
    def register(cls, provider: str, creator: VectorStoreCreator) -> None:
        """Register a vector store provider by name."""
        normalized = _normalize_provider(provider)
        cls._registry[normalized] = creator

    @classmethod
    def unregister(cls, provider: str) -> None:
        """Remove a vector store provider registration if present."""
        cls._registry.pop(_normalize_provider(provider), None)

    @classmethod
    def create(cls, settings: Settings | VectorStoreSettings | Any) -> BaseVectorStore:
        """Create a vector store from Settings or VectorStoreSettings."""
        vector_store_settings = _extract_vector_store_settings(settings)
        provider = _normalize_provider(vector_store_settings.provider)
        creator = cls._registry.get(provider)
        if creator is None:
            available = ", ".join(sorted(cls._registry)) or "none"
            raise VectorStoreFactoryError(
                f"Unsupported vector store provider '{vector_store_settings.provider}'. "
                f"Registered providers: {available}"
            )
        return creator(vector_store_settings)


def _extract_vector_store_settings(
    settings: Settings | VectorStoreSettings | Any,
) -> VectorStoreSettings:
    if isinstance(settings, VectorStoreSettings):
        return settings
    vector_store_settings = getattr(settings, "vector_store", None)
    if isinstance(vector_store_settings, VectorStoreSettings):
        return vector_store_settings
    raise VectorStoreFactoryError(
        "VectorStoreFactory.create expects Settings or VectorStoreSettings"
    )


def _normalize_provider(provider: str) -> str:
    if not provider or not provider.strip():
        raise VectorStoreFactoryError("Vector store provider must be a non-empty string")
    return provider.strip().lower().replace("_", "-")


from .chroma_store import ChromaStore


VectorStoreFactory.register("chroma", ChromaStore)
