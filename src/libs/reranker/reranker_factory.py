"""Factory for pluggable rerankers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.settings import RerankSettings, Settings

from .base_reranker import BaseReranker
from .llm_reranker import LLMReranker
from .none_reranker import NoneReranker


class RerankerFactoryError(ValueError):
    """Raised when a reranker provider cannot be created."""


RerankerCreator = Callable[[RerankSettings], BaseReranker]


class RerankerFactory:
    """Create reranker implementations from project settings."""

    _registry: dict[str, RerankerCreator] = {
        "llm": LLMReranker,
        "none": NoneReranker,
    }

    @classmethod
    def register(cls, provider: str, creator: RerankerCreator) -> None:
        """Register a reranker provider by name."""
        normalized = _normalize_provider(provider)
        cls._registry[normalized] = creator

    @classmethod
    def unregister(cls, provider: str) -> None:
        """Remove a reranker provider registration if present."""
        normalized = _normalize_provider(provider)
        if normalized == "none":
            cls._registry[normalized] = NoneReranker
            return
        cls._registry.pop(normalized, None)

    @classmethod
    def create(cls, settings: Settings | RerankSettings | Any) -> BaseReranker:
        """Create a reranker from Settings or RerankSettings."""
        rerank_settings = _extract_rerank_settings(settings)
        if not rerank_settings.enabled:
            return NoneReranker(rerank_settings)

        provider = _normalize_provider(rerank_settings.provider)
        creator = cls._registry.get(provider)
        if creator is None:
            available = ", ".join(sorted(cls._registry)) or "none"
            raise RerankerFactoryError(
                f"Unsupported reranker provider '{rerank_settings.provider}'. "
                f"Registered providers: {available}"
            )
        return creator(rerank_settings)


def _extract_rerank_settings(
    settings: Settings | RerankSettings | Any,
) -> RerankSettings:
    if isinstance(settings, RerankSettings):
        return settings
    rerank_settings = getattr(settings, "rerank", None)
    if isinstance(rerank_settings, RerankSettings):
        return rerank_settings
    raise RerankerFactoryError("RerankerFactory.create expects Settings or RerankSettings")


def _normalize_provider(provider: str) -> str:
    if not provider or not provider.strip():
        raise RerankerFactoryError("Reranker provider must be a non-empty string")
    return provider.strip().lower().replace("_", "-")
