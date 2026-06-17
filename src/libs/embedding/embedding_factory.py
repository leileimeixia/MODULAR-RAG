"""Factory for pluggable embedding providers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.settings import EmbeddingSettings, Settings

from .base_embedding import BaseEmbedding


class EmbeddingFactoryError(ValueError):
    """Raised when an embedding provider cannot be created."""


EmbeddingCreator = Callable[[EmbeddingSettings], BaseEmbedding]


class EmbeddingFactory:
    """Create embedding implementations from project settings."""

    _registry: dict[str, EmbeddingCreator] = {}

    @classmethod
    def register(cls, provider: str, creator: EmbeddingCreator) -> None:
        """Register a provider creator by provider name."""
        normalized = _normalize_provider(provider)
        cls._registry[normalized] = creator

    @classmethod
    def unregister(cls, provider: str) -> None:
        """Remove a provider registration if present."""
        cls._registry.pop(_normalize_provider(provider), None)

    @classmethod
    def create(cls, settings: Settings | EmbeddingSettings | Any) -> BaseEmbedding:
        """Create an embedding client from Settings or EmbeddingSettings."""
        embedding_settings = _extract_embedding_settings(settings)
        provider = _normalize_provider(embedding_settings.provider)
        creator = cls._registry.get(provider)
        if creator is None:
            available = ", ".join(sorted(cls._registry)) or "none"
            raise EmbeddingFactoryError(
                f"Unsupported embedding provider '{embedding_settings.provider}'. "
                f"Registered providers: {available}"
            )
        return creator(embedding_settings)


def _extract_embedding_settings(
    settings: Settings | EmbeddingSettings | Any,
) -> EmbeddingSettings:
    if isinstance(settings, EmbeddingSettings):
        return settings
    embedding_settings = getattr(settings, "embedding", None)
    if isinstance(embedding_settings, EmbeddingSettings):
        return embedding_settings
    raise EmbeddingFactoryError(
        "EmbeddingFactory.create expects Settings or EmbeddingSettings"
    )


def _normalize_provider(provider: str) -> str:
    if not provider or not provider.strip():
        raise EmbeddingFactoryError("Embedding provider must be a non-empty string")
    return provider.strip().lower().replace("_", "-")
