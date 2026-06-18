"""Custom lightweight retrieval metrics."""

from __future__ import annotations

from typing import Any

from core.settings import EvaluationSettings

from .base_evaluator import BaseEvaluator, EvaluationResult


class CustomEvaluator(BaseEvaluator):
    """Compute deterministic retrieval metrics without external dependencies."""

    def __init__(self, settings: EvaluationSettings | None = None) -> None:
        self.settings = settings

    def evaluate(
        self,
        query: str,
        retrieved_ids: list[str],
        golden_ids: list[str],
        generated_answer: str = "",
        trace: Any | None = None,
    ) -> EvaluationResult:
        """Return hit rate, MRR, and precision over retrieved ids."""
        golden_set = set(golden_ids)
        retrieved_count = len(retrieved_ids)

        if not golden_set or not retrieved_ids:
            return EvaluationResult(
                metrics={
                    "hit_rate": 0.0,
                    "mrr": 0.0,
                    "precision": 0.0,
                },
                details={
                    "query": query,
                    "retrieved_count": retrieved_count,
                    "golden_count": len(golden_set),
                    "first_hit_rank": None,
                },
            )

        first_hit_rank = _first_hit_rank(retrieved_ids, golden_set)
        hit_count = sum(1 for retrieved_id in retrieved_ids if retrieved_id in golden_set)

        return EvaluationResult(
            metrics={
                "hit_rate": 1.0 if first_hit_rank is not None else 0.0,
                "mrr": 0.0 if first_hit_rank is None else 1.0 / first_hit_rank,
                "precision": hit_count / retrieved_count,
            },
            details={
                "query": query,
                "retrieved_count": retrieved_count,
                "golden_count": len(golden_set),
                "first_hit_rank": first_hit_rank,
            },
        )


def _first_hit_rank(retrieved_ids: list[str], golden_ids: set[str]) -> int | None:
    for index, retrieved_id in enumerate(retrieved_ids, start=1):
        if retrieved_id in golden_ids:
            return index
    return None
