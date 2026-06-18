"""Base abstractions for retrieval evaluators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


MetricMap = dict[str, float]


@dataclass(frozen=True)
class EvaluationResult:
    """Standard result returned by evaluator implementations."""

    metrics: MetricMap
    details: dict[str, Any] = field(default_factory=dict)


class BaseEvaluator(ABC):
    """Common interface for lightweight and framework-backed evaluators."""

    @abstractmethod
    def evaluate(
        self,
        query: str,
        retrieved_ids: list[str],
        golden_ids: list[str],
        generated_answer: str = "",
        trace: Any | None = None,
    ) -> EvaluationResult:
        """Evaluate retrieved results against golden ids."""
