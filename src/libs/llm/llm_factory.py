"""Factory for pluggable LLM providers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.settings import LLMSettings, Settings, VisionLLMSettings

from .base_llm import BaseLLM
from .base_vision_llm import BaseVisionLLM


class LLMFactoryError(ValueError):
    """Raised when an LLM provider cannot be created."""


LLMCreator = Callable[[LLMSettings], BaseLLM]
VisionLLMCreator = Callable[[VisionLLMSettings], BaseVisionLLM]


class LLMFactory:
    """Create LLM implementations from project settings."""

    _registry: dict[str, LLMCreator] = {}
    _vision_registry: dict[str, VisionLLMCreator] = {}

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
    def register_vision(cls, provider: str, creator: VisionLLMCreator) -> None:
        """Register a vision LLM provider by name."""
        normalized = _normalize_provider(provider)
        cls._vision_registry[normalized] = creator

    @classmethod
    def unregister_vision(cls, provider: str) -> None:
        """Remove a vision LLM provider registration if present."""
        cls._vision_registry.pop(_normalize_provider(provider), None)

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

    @classmethod
    def create_vision_llm(
        cls,
        settings: Settings | VisionLLMSettings | Any,
    ) -> BaseVisionLLM:
        """Create a vision LLM from Settings or VisionLLMSettings."""
        vision_settings = _extract_vision_llm_settings(settings)
        if not vision_settings.enabled:
            raise LLMFactoryError("Vision LLM is disabled in settings")

        provider = _normalize_provider(vision_settings.provider)
        creator = cls._vision_registry.get(provider)
        if creator is None:
            available = ", ".join(sorted(cls._vision_registry)) or "none"
            raise LLMFactoryError(
                f"Unsupported vision LLM provider '{vision_settings.provider}'. "
                f"Registered providers: {available}"
            )
        return creator(vision_settings)


def _extract_llm_settings(settings: Settings | LLMSettings | Any) -> LLMSettings:
    if isinstance(settings, LLMSettings):
        return settings
    llm_settings = getattr(settings, "llm", None)
    if isinstance(llm_settings, LLMSettings):
        return llm_settings
    raise LLMFactoryError("LLMFactory.create expects Settings or LLMSettings")


def _extract_vision_llm_settings(
    settings: Settings | VisionLLMSettings | Any,
) -> VisionLLMSettings:
    if isinstance(settings, VisionLLMSettings):
        return settings
    vision_settings = getattr(settings, "vision_llm", None)
    if isinstance(vision_settings, VisionLLMSettings):
        return vision_settings
    raise LLMFactoryError(
        "LLMFactory.create_vision_llm expects Settings or VisionLLMSettings"
    )


def _normalize_provider(provider: str) -> str:
    if not provider or not provider.strip():
        raise LLMFactoryError("LLM provider must be a non-empty string")
    return provider.strip().lower().replace("_", "-")


from .azure_llm import AzureLLM
from .deepseek_llm import DeepSeekLLM
from .ollama_llm import OllamaLLM
from .openai_llm import OpenAILLM


LLMFactory.register("azure", AzureLLM)
LLMFactory.register("azure-openai", AzureLLM)
LLMFactory.register("deepseek", DeepSeekLLM)
LLMFactory.register("ollama", OllamaLLM)
LLMFactory.register("openai", OpenAILLM)
