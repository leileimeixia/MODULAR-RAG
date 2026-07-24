"""Tests for composite evaluator orchestration."""

from __future__ import annotations

from typing import Any

import pytest

from core.settings import EvaluationSettings
from libs.evaluator import BaseEvaluator, EvaluationResult, EvaluatorFactory
from observability.evaluation.composite_evaluator import (
    CompositeEvaluator,
    CompositeEvaluatorError,
)


class FakeEvaluator(BaseEvaluator):
    def __init__(
        self,
        metrics: dict[str, float],
        details: dict[str, Any] | None = None,
    ) -> None:
        self.metrics = metrics
        self.details = details or {}
        self.calls: list[dict[str, Any]] = []

    def evaluate(
        self,
        query: str,
        retrieved_ids: list[str],
        golden_ids: list[str],
        generated_answer: str = "",
        trace: Any | None = None,
    ) -> EvaluationResult:
        self.calls.append(
            {
                "query": query,
                "retrieved_ids": retrieved_ids,
                "golden_ids": golden_ids,
                "generated_answer": generated_answer,
                "trace": trace,
            }
        )
        return EvaluationResult(metrics=dict(self.metrics), details=dict(self.details))


class FailingEvaluator(BaseEvaluator):
    def evaluate(
        self,
        query: str,
        retrieved_ids: list[str],
        golden_ids: list[str],
        generated_answer: str = "",
        trace: Any | None = None,
    ) -> EvaluationResult:
        raise RuntimeError("backend failed")


class FactoryFakeEvaluator(BaseEvaluator):
    def __init__(self, settings: EvaluationSettings) -> None:
        self.settings = settings

    def evaluate(
        self,
        query: str,
        retrieved_ids: list[str],
        golden_ids: list[str],
        generated_answer: str = "",
        trace: Any | None = None,
    ) -> EvaluationResult:
        return EvaluationResult(metrics={self.settings.provider: 1.0})


class FakeTrace:
    def __init__(self) -> None:
        self.stages: list[dict[str, Any]] = []

    def record_stage(
        self,
        stage: str,
        method: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.stages.append({"stage": stage, "method": method, "details": details or {}})


@pytest.fixture(autouse=True)
def clean_registry() -> None:
    EvaluatorFactory.unregister("factory-a")
    EvaluatorFactory.unregister("factory-b")
    yield
    EvaluatorFactory.unregister("factory-a")
    EvaluatorFactory.unregister("factory-b")


def test_composite_evaluator_merges_metrics_from_multiple_backends() -> None:
    first = FakeEvaluator({"hit_rate": 1.0}, {"source": "custom"})
    second = FakeEvaluator(
        {
            "faithfulness": 0.8,
            "answer_relevancy": 0.7,
        },
        {"source": "ragas"},
    )
    evaluator = CompositeEvaluator([first, second], max_workers=2)

    result = evaluator.evaluate(
        "What is RAG?",
        ["chunk-a"],
        ["chunk-a"],
        "Retrieval augmented generation.",
    )

    assert result.metrics == {
        "hit_rate": 1.0,
        "faithfulness": 0.8,
        "answer_relevancy": 0.7,
    }
    assert result.details["evaluator_count"] == 2
    assert result.details["errors"] == []
    assert first.calls[0]["query"] == "What is RAG?"
    assert second.calls[0]["retrieved_ids"] == ["chunk-a"]


def test_composite_evaluator_namespaces_duplicate_metric_keys() -> None:
    evaluator = CompositeEvaluator(
        [
            FakeEvaluator({"score": 0.4}),
            FakeEvaluator({"score": 0.9}),
        ]
    )

    result = evaluator.evaluate("query", ["a"], ["a"])

    assert result.metrics == {
        "score": 0.4,
        "FakeEvaluator.score": 0.9,
    }


def test_composite_evaluator_keeps_successful_metrics_when_one_backend_fails() -> None:
    evaluator = CompositeEvaluator([FailingEvaluator(), FakeEvaluator({"hit_rate": 1.0})])

    result = evaluator.evaluate("query", ["a"], ["a"])

    assert result.metrics == {"hit_rate": 1.0}
    assert result.details["errors"] == [
        {
            "evaluator": "1:FailingEvaluator",
            "error": "backend failed",
        }
    ]


def test_composite_evaluator_raises_when_all_backends_fail() -> None:
    evaluator = CompositeEvaluator([FailingEvaluator()])

    with pytest.raises(CompositeEvaluatorError, match="all evaluators failed"):
        evaluator.evaluate("query", ["a"], ["a"])


def test_factory_builds_composite_from_evaluation_backends() -> None:
    EvaluatorFactory.register("factory-a", FactoryFakeEvaluator)
    EvaluatorFactory.register("factory-b", FactoryFakeEvaluator)

    evaluator = EvaluatorFactory.create(
        EvaluationSettings(
            enabled=True,
            provider="composite",
            backends=["factory-a", "factory-b"],
        )
    )

    assert isinstance(evaluator, CompositeEvaluator)
    result = evaluator.evaluate("query", ["a"], ["a"])
    assert result.metrics == {
        "factory-a": 1.0,
        "factory-b": 1.0,
    }


def test_composite_evaluator_records_trace_summary() -> None:
    trace = FakeTrace()
    evaluator = CompositeEvaluator([FakeEvaluator({"hit_rate": 1.0})])

    evaluator.evaluate("query", ["a"], ["a"], trace=trace)

    assert trace.stages[-1] == {
        "stage": "composite_evaluation",
        "method": "CompositeEvaluator",
        "details": {
            "evaluator_count": 1,
            "metric_count": 1,
            "error_count": 0,
        },
    }
