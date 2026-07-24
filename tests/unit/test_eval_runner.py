"""Tests for golden test set evaluation runner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from core import RetrievalResult
from libs.evaluator import BaseEvaluator, EvaluationResult
from observability.evaluation.eval_runner import (
    EvalRunner,
    EvalRunnerError,
    load_golden_test_set,
)


@dataclass(frozen=True)
class FakeRetrievalSettings:
    fusion_top_k: int = 5


@dataclass(frozen=True)
class FakeSettings:
    retrieval: FakeRetrievalSettings = FakeRetrievalSettings()


class FakeHybridSearch:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def search(self, query: str, top_k: int, filters=None):
        self.calls.append({"query": query, "top_k": top_k, "filters": filters})
        return [
            RetrievalResult(
                chunk_id="chunk-a",
                score=0.9,
                text="alpha",
                metadata={"source_path": "docs/a.md"},
            ),
            RetrievalResult(
                chunk_id="chunk-b",
                score=0.5,
                text="beta",
                metadata={"source_path": "docs/b.md"},
            ),
        ]


class FakeEvaluator(BaseEvaluator):
    def __init__(self) -> None:
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
            }
        )
        return EvaluationResult(
            metrics={
                "hit_rate": 1.0 if golden_ids[0] in retrieved_ids else 0.0,
                "mrr": 1.0,
            },
            details={"first_hit_rank": 1},
        )


def _write_test_set(tmp_path, payload: dict[str, Any]):
    path = tmp_path / "golden_test_set.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_eval_runner_loads_cases_runs_search_and_aggregates_metrics(tmp_path) -> None:
    path = _write_test_set(
        tmp_path,
        {
            "test_cases": [
                {
                    "query": "alpha?",
                    "expected_chunk_ids": ["chunk-a"],
                    "expected_sources": ["docs/a.md"],
                    "generated_answer": "alpha answer",
                    "top_k": 2,
                    "filters": {"collection": "docs"},
                },
                {
                    "query": "beta?",
                    "expected_chunk_ids": ["chunk-b"],
                    "generated_answer": "beta answer",
                },
            ]
        },
    )
    hybrid_search = FakeHybridSearch()
    evaluator = FakeEvaluator()

    report = EvalRunner(
        settings=FakeSettings(),
        hybrid_search=hybrid_search,
        evaluator=evaluator,
    ).run(path)

    assert report.metrics == {"hit_rate": 1.0, "mrr": 1.0}
    assert report.details == {"test_set_path": str(path), "case_count": 2}
    assert [result.query for result in report.case_results] == ["alpha?", "beta?"]
    assert hybrid_search.calls == [
        {"query": "alpha?", "top_k": 2, "filters": {"collection": "docs"}},
        {"query": "beta?", "top_k": 5, "filters": None},
    ]
    assert evaluator.calls[0]["retrieved_ids"] == ["chunk-a", "chunk-b"]
    assert evaluator.calls[0]["golden_ids"] == ["chunk-a"]
    assert report.to_dict()["case_results"][0]["details"]["expected_sources"] == [
        "docs/a.md"
    ]


def test_load_golden_test_set_rejects_missing_cases(tmp_path) -> None:
    path = _write_test_set(tmp_path, {"test_cases": []})

    with pytest.raises(EvalRunnerError, match="at least one test case"):
        load_golden_test_set(path)


def test_load_golden_test_set_rejects_invalid_expected_ids(tmp_path) -> None:
    path = _write_test_set(
        tmp_path,
        {"test_cases": [{"query": "alpha?", "expected_chunk_ids": []}]},
    )

    with pytest.raises(EvalRunnerError, match="expected_chunk_ids"):
        load_golden_test_set(path)
