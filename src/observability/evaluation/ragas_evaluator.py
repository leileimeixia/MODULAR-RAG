"""Ragas-backed evaluator with optional dependency loading."""

from __future__ import annotations

from collections.abc import Callable
from statistics import fmean
from typing import Any

from core.settings import EvaluationSettings
from libs.evaluator.base_evaluator import BaseEvaluator, EvaluationResult


DEFAULT_RAGAS_METRICS = (
    "faithfulness",
    "answer_relevancy",
    "context_precision",
)

RagasRunner = Callable[[dict[str, Any], list[str]], Any]


class RagasEvaluator(BaseEvaluator):
    """Evaluate RAG answers through Ragas when the optional package is available."""

    def __init__(
        self,
        settings: EvaluationSettings | None = None,
        evaluator: RagasRunner | None = None,
        metrics: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.settings = settings
        self._evaluator = evaluator
        self.metrics = tuple(metrics or DEFAULT_RAGAS_METRICS)

    def evaluate(
        self,
        query: str,
        retrieved_ids: list[str],
        golden_ids: list[str],
        generated_answer: str = "",
        trace: Any | None = None,
    ) -> EvaluationResult:
        """Return normalized Ragas metrics for one query-answer sample."""
        _validate_inputs(query, retrieved_ids, golden_ids, generated_answer)
        payload = _build_ragas_payload(query, retrieved_ids, golden_ids, generated_answer)
        runner = self._evaluator or _load_ragas_runner()
        raw_result = runner(payload, list(self.metrics))
        metrics = _normalize_metrics(raw_result)
        details = {
            "query": query,
            "retrieved_count": len(retrieved_ids),
            "golden_count": len(golden_ids),
            "metric_names": list(self.metrics),
            "context_source": "retrieved_ids",
        }

        if trace is not None:
            trace.record_stage(
                "ragas_evaluation",
                method="RagasEvaluator",
                details={
                    **details,
                    "metrics": dict(metrics),
                },
            )

        return EvaluationResult(metrics=metrics, details=details)


def _validate_inputs(
    query: str,
    retrieved_ids: list[str],
    golden_ids: list[str],
    generated_answer: str,
) -> None:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if not isinstance(retrieved_ids, list) or not all(
        isinstance(item, str) for item in retrieved_ids
    ):
        raise ValueError("retrieved_ids must be a list of strings")
    if not isinstance(golden_ids, list) or not all(
        isinstance(item, str) for item in golden_ids
    ):
        raise ValueError("golden_ids must be a list of strings")
    if not isinstance(generated_answer, str):
        raise ValueError("generated_answer must be a string")


def _build_ragas_payload(
    query: str,
    retrieved_ids: list[str],
    golden_ids: list[str],
    generated_answer: str,
) -> dict[str, Any]:
    return {
        "question": query,
        "answer": generated_answer,
        "contexts": list(retrieved_ids),
        "ground_truth": "\n".join(golden_ids),
        "retrieved_ids": list(retrieved_ids),
        "golden_ids": list(golden_ids),
    }


def _load_ragas_runner() -> RagasRunner:
    try:
        from ragas import evaluate as ragas_evaluate  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ImportError(
            "RagasEvaluator requires the optional 'ragas' package. "
            "Install it with `pip install ragas`, or inject an evaluator callable."
        ) from exc

    def _runner(payload: dict[str, Any], metrics: list[str]) -> Any:
        return ragas_evaluate([payload], metrics=metrics)

    return _runner


def _normalize_metrics(raw_result: Any) -> dict[str, float]:
    if isinstance(raw_result, dict):
        return _numeric_metrics(raw_result)
    if hasattr(raw_result, "scores") and isinstance(raw_result.scores, dict):
        return _numeric_metrics(raw_result.scores)
    if hasattr(raw_result, "to_pandas"):
        frame = raw_result.to_pandas()
        if getattr(frame, "empty", True):
            return {}
        return _numeric_metrics(frame.iloc[0].to_dict())
    return {}


def _numeric_metrics(values: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for key, value in values.items():
        number = _to_float(value)
        if number is not None:
            metrics[str(key)] = number
    return metrics


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, list | tuple):
        numbers = [_to_float(item) for item in value]
        filtered = [number for number in numbers if number is not None]
        return fmean(filtered) if filtered else None
    return None
