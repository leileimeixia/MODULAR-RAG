"""Composite evaluator for running multiple evaluators together."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from libs.evaluator.base_evaluator import BaseEvaluator, EvaluationResult


class CompositeEvaluatorError(ValueError):
    """Raised when a composite evaluator cannot produce a result."""


class CompositeEvaluator(BaseEvaluator):
    """Run multiple evaluators and merge their metric outputs."""

    def __init__(
        self,
        evaluators: list[BaseEvaluator],
        max_workers: int | None = None,
    ) -> None:
        if not evaluators:
            raise CompositeEvaluatorError("CompositeEvaluator requires at least one evaluator")
        self.evaluators = list(evaluators)
        self.max_workers = max_workers

    def evaluate(
        self,
        query: str,
        retrieved_ids: list[str],
        golden_ids: list[str],
        generated_answer: str = "",
        trace: Any | None = None,
    ) -> EvaluationResult:
        """Evaluate one sample with all configured evaluators."""
        workers = self.max_workers or len(self.evaluators)
        merged_metrics: dict[str, float] = {}
        metrics_by_evaluator: dict[str, dict[str, float]] = {}
        details_by_evaluator: dict[str, dict[str, Any]] = {}
        errors: list[dict[str, str]] = []
        results: list[tuple[int, str, EvaluationResult]] = []

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    evaluator.evaluate,
                    query,
                    list(retrieved_ids),
                    list(golden_ids),
                    generated_answer,
                    trace,
                ): (index, evaluator)
                for index, evaluator in enumerate(self.evaluators)
            }

            for future in as_completed(futures):
                index, evaluator = futures[future]
                label = _evaluator_label(evaluator, index)
                try:
                    result = future.result()
                except Exception as exc:  # noqa: BLE001 - one backend should not hide others.
                    errors.append(
                        {
                            "evaluator": label,
                            "error": str(exc),
                        }
                    )
                    continue
                results.append((index, label, result))

        for _index, label, result in sorted(results, key=lambda item: item[0]):
            metrics_by_evaluator[label] = dict(result.metrics)
            details_by_evaluator[label] = dict(result.details)
            _merge_metrics(merged_metrics, result.metrics, label)

        if not merged_metrics and errors:
            raise CompositeEvaluatorError("all evaluators failed")

        details = {
            "query": query,
            "evaluator_count": len(self.evaluators),
            "metrics_by_evaluator": metrics_by_evaluator,
            "details_by_evaluator": details_by_evaluator,
            "errors": errors,
        }
        if trace is not None:
            trace.record_stage(
                "composite_evaluation",
                method="CompositeEvaluator",
                details={
                    "evaluator_count": len(self.evaluators),
                    "metric_count": len(merged_metrics),
                    "error_count": len(errors),
                },
            )
        return EvaluationResult(metrics=merged_metrics, details=details)


def _evaluator_label(evaluator: BaseEvaluator, index: int) -> str:
    return f"{index + 1}:{evaluator.__class__.__name__}"


def _merge_metrics(
    target: dict[str, float],
    metrics: dict[str, float],
    evaluator_label: str,
) -> None:
    prefix = evaluator_label.split(":", 1)[1]
    for key, value in metrics.items():
        metric_key = key if key not in target else f"{prefix}.{key}"
        target[metric_key] = value
