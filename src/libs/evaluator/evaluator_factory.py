"""Factory for pluggable evaluator providers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.settings import EvaluationSettings, Settings

from .base_evaluator import BaseEvaluator
from .custom_evaluator import CustomEvaluator


class EvaluatorFactoryError(ValueError):
    """Raised when an evaluator provider cannot be created."""


EvaluatorCreator = Callable[[EvaluationSettings], BaseEvaluator]


def _create_ragas_evaluator(settings: EvaluationSettings) -> BaseEvaluator:
    from observability.evaluation.ragas_evaluator import RagasEvaluator

    return RagasEvaluator(settings)


class EvaluatorFactory:
    """Create evaluator implementations from project settings."""

    _registry: dict[str, EvaluatorCreator] = {
        "custom": CustomEvaluator,
        "ragas": _create_ragas_evaluator,
    }

    @classmethod
    def register(cls, provider: str, creator: EvaluatorCreator) -> None:
        """Register an evaluator provider by name."""
        cls._registry[_normalize_provider(provider)] = creator

    @classmethod
    def unregister(cls, provider: str) -> None:
        """Remove an evaluator provider registration if present."""
        normalized = _normalize_provider(provider)
        if normalized == "custom":
            cls._registry[normalized] = CustomEvaluator
            return
        cls._registry.pop(normalized, None)

    @classmethod
    def create(cls, settings: Settings | EvaluationSettings | Any) -> BaseEvaluator:
        """Create an evaluator from Settings or EvaluationSettings."""
        evaluation_settings = _extract_evaluation_settings(settings)
        provider = _normalize_provider(evaluation_settings.provider)
        creator = cls._registry.get(provider)
        if creator is None:
            available = ", ".join(sorted(cls._registry)) or "none"
            raise EvaluatorFactoryError(
                f"Unsupported evaluator provider '{evaluation_settings.provider}'. "
                f"Registered providers: {available}"
            )
        return creator(evaluation_settings)


def _extract_evaluation_settings(
    settings: Settings | EvaluationSettings | Any,
) -> EvaluationSettings:
    if isinstance(settings, EvaluationSettings):
        return settings
    evaluation_settings = getattr(settings, "evaluation", None)
    if isinstance(evaluation_settings, EvaluationSettings):
        return evaluation_settings
    raise EvaluatorFactoryError(
        "EvaluatorFactory.create expects Settings or EvaluationSettings"
    )


def _normalize_provider(provider: str) -> str:
    if not provider or not provider.strip():
        raise EvaluatorFactoryError("Evaluator provider must be a non-empty string")
    return provider.strip().lower().replace("_", "-")
