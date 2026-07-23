"""Tests for the optional Ragas evaluator wrapper."""

from __future__ import annotations

from typing import Any

import pytest

from core.settings import EvaluationSettings
from libs.evaluator import EvaluatorFactory
from observability.evaluation.ragas_evaluator import RagasEvaluator


class FakeTrace:
    def __init__(self) -> None:
        self.stages: list[dict[str, Any]] = []

    def record_stage(
        self,
        stage: str,
        method: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.stages.append(
            {
                "stage": stage,
                "method": method,
                "details": details or {},
            }
        )


def test_ragas_evaluator_returns_mocked_metrics() -> None:
    def fake_runner(payload: dict[str, Any], metrics: list[str]) -> dict[str, float]:
        assert payload["question"] == "What is RAG?"
        assert payload["answer"] == "Retrieval augmented generation."
        assert payload["contexts"] == ["chunk-a", "chunk-b"]
        assert payload["ground_truth"] == "chunk-a"
        assert metrics == [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
        ]
        return {
            "faithfulness": 0.9,
            "answer_relevancy": 0.8,
            "context_precision": 0.7,
        }

    evaluator = RagasEvaluator(
        EvaluationSettings(enabled=True, provider="ragas"),
        evaluator=fake_runner,
    )

    result = evaluator.evaluate(
        query="What is RAG?",
        retrieved_ids=["chunk-a", "chunk-b"],
        golden_ids=["chunk-a"],
        generated_answer="Retrieval augmented generation.",
    )

    assert result.metrics == {
        "faithfulness": 0.9,
        "answer_relevancy": 0.8,
        "context_precision": 0.7,
    }
    assert result.details["retrieved_count"] == 2
    assert result.details["golden_count"] == 1
    assert result.details["context_source"] == "retrieved_ids"


def test_factory_creates_ragas_evaluator_without_importing_ragas() -> None:
    evaluator = EvaluatorFactory.create(EvaluationSettings(enabled=True, provider="ragas"))

    assert isinstance(evaluator, RagasEvaluator)


def test_ragas_evaluator_raises_clear_error_when_dependency_missing(monkeypatch) -> None:
    def missing_runner() -> None:
        raise ImportError(
            "RagasEvaluator requires the optional 'ragas' package. "
            "Install it with `pip install ragas`, or inject an evaluator callable."
        )

    monkeypatch.setattr(
        "observability.evaluation.ragas_evaluator._load_ragas_runner",
        missing_runner,
    )
    evaluator = RagasEvaluator(EvaluationSettings(enabled=True, provider="ragas"))

    with pytest.raises(ImportError, match="optional 'ragas' package"):
        evaluator.evaluate("What is RAG?", ["chunk-a"], ["chunk-a"], "answer")


def test_ragas_evaluator_normalizes_list_metric_values() -> None:
    evaluator = RagasEvaluator(
        evaluator=lambda _payload, _metrics: {
            "faithfulness": [0.5, 1.0],
            "answer_relevancy": 0.25,
            "ignored": "not numeric",
        }
    )

    result = evaluator.evaluate("What is RAG?", ["chunk-a"], ["chunk-a"], "answer")

    assert result.metrics == {
        "faithfulness": 0.75,
        "answer_relevancy": 0.25,
    }


def test_ragas_evaluator_records_trace_stage() -> None:
    trace = FakeTrace()
    evaluator = RagasEvaluator(
        evaluator=lambda _payload, _metrics: {
            "faithfulness": 1.0,
            "answer_relevancy": 0.5,
        }
    )

    evaluator.evaluate("What is RAG?", ["chunk-a"], ["chunk-a"], "answer", trace=trace)

    assert trace.stages == [
        {
            "stage": "ragas_evaluation",
            "method": "RagasEvaluator",
            "details": {
                "query": "What is RAG?",
                "retrieved_count": 1,
                "golden_count": 1,
                "metric_names": [
                    "faithfulness",
                    "answer_relevancy",
                    "context_precision",
                ],
                "context_source": "retrieved_ids",
                "metrics": {
                    "faithfulness": 1.0,
                    "answer_relevancy": 0.5,
                },
            },
        }
    ]
