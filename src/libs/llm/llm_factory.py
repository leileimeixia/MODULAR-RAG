"""Factory for pluggable LLM providers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.settings import LLMSettings, Settings

from .base_llm import BaseLLM


class LLMFactoryError(ValueError):
    """Raised when an LLM provider cannot be created."""


LLMCreator = Callable[[LLMSettings], BaseLLM]


class LLMFactory:
    """Create LLM implementations from project settings."""

    _registry: dict[str, LLMCreator] = {}

    @classmethod
    def register(cls, provider: str, creator: LLMCreator) -> None:
        """Register a provider creator by provider name."""
        normalized = _normalize_provider(provider)
        cls._registry[normalized] = creator

    @classmethod
    def unregister(cls, provider: str) -> None:
        """Remove a provider registration if present."""
        cls._registry.pop(_normalize_provider(provider), None)

    @classmethod
    def create(cls, settings: Settings | LLMSettings | Any) -> BaseLLM:
        """Create an LLM from a full Settings object or an LLMSettings object."""
        llm_settings = _extract_llm_settings(settings)
        provider = _normalize_provider(llm_settings.provider)
        creator = cls._registry.get(provider)
        if creator is None:
            available = ", ".join(sorted(cls._registry)) or "none"
            raise LLMFactoryError(
                f"Unsupported LLM provider '{llm_settings.provider}'. "
                f"Registered providers: {available}"
            )
        return creator(llm_settings)


def _extract_llm_settings(settings: Settings | LLMSettings | Any) -> LLMSettings:
    if isinstance(settings, LLMSettings):
        return settings
    llm_settings = getattr(settings, "llm", None)
    if isinstance(llm_settings, LLMSettings):
        return llm_settings
    raise LLMFactoryError("LLMFactory.create expects Settings or LLMSettings")


def _normalize_provider(provider: str) -> str:
    if not provider or not provider.strip():
        raise LLMFactoryError("LLM provider must be a non-empty string")
    return provider.strip().lower().replace("_", "-")
