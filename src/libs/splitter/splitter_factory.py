"""Factory for pluggable text splitters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.settings import Settings, SplitterSettings

from .base_splitter import BaseSplitter


class SplitterFactoryError(ValueError):
    """Raised when a splitter provider cannot be created."""


SplitterCreator = Callable[[SplitterSettings], BaseSplitter]


class SplitterFactory:
    """Create splitter implementations from project settings."""

    _registry: dict[str, SplitterCreator] = {}

    @classmethod
    def register(cls, provider: str, creator: SplitterCreator) -> None:
        """Register a splitter provider by name."""
        normalized = _normalize_provider(provider)
        cls._registry[normalized] = creator

    @classmethod
    def unregister(cls, provider: str) -> None:
        """Remove a splitter provider registration if present."""
        cls._registry.pop(_normalize_provider(provider), None)

    @classmethod
    def create(cls, settings: Settings | SplitterSettings | Any) -> BaseSplitter:
        """Create a splitter from Settings or SplitterSettings."""
        splitter_settings = _extract_splitter_settings(settings)
        provider = _normalize_provider(splitter_settings.provider)
        creator = cls._registry.get(provider)
        if creator is None:
            available = ", ".join(sorted(cls._registry)) or "none"
            raise SplitterFactoryError(
                f"Unsupported splitter provider '{splitter_settings.provider}'. "
                f"Registered providers: {available}"
            )
        return creator(splitter_settings)


def _extract_splitter_settings(
    settings: Settings | SplitterSettings | Any,
) -> SplitterSettings:
    if isinstance(settings, SplitterSettings):
        return settings
    splitter_settings = getattr(settings, "splitter", None)
    if isinstance(splitter_settings, SplitterSettings):
        return splitter_settings
    raise SplitterFactoryError("SplitterFactory.create expects Settings or SplitterSettings")


def _normalize_provider(provider: str) -> str:
    if not provider or not provider.strip():
        raise SplitterFactoryError("Splitter provider must be a non-empty string")
    return provider.strip().lower().replace("_", "-")


from .recursive_splitter import RecursiveSplitter


SplitterFactory.register("recursive", RecursiveSplitter)
