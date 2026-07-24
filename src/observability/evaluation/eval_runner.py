"""Run golden test set evaluation against the retrieval pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from statistics import fmean
from typing import Any

from core import RetrievalResult
from libs.evaluator.base_evaluator import BaseEvaluator, EvaluationResult


class EvalRunnerError(ValueError):
    """Raised when evaluation cannot be executed."""


@dataclass(frozen=True)
class EvalCase:
    """One golden evaluation case."""

    query: str
    expected_chunk_ids: list[str]
    expected_sources: list[str] = field(default_factory=list)
    generated_answer: str = ""
    top_k: int | None = None
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalCaseResult:
    """Evaluation output for one golden case."""

    query: str
    retrieved_ids: list[str]
    expected_chunk_ids: list[str]
    metrics: dict[str, float]
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalReport:
    """Aggregated evaluation report."""

    metrics: dict[str, float]
    case_results: list[EvalCaseResult]
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize report to a JSON-compatible dictionary."""
        return {
            "metrics": dict(self.metrics),
            "case_results": [
                {
                    "query": result.query,
                    "retrieved_ids": list(result.retrieved_ids),
                    "expected_chunk_ids": list(result.expected_chunk_ids),
                    "metrics": dict(result.metrics),
                    "details": dict(result.details),
                }
                for result in self.case_results
            ],
            "details": dict(self.details),
        }


class EvalRunner:
    """Load golden cases, run retrieval, and aggregate evaluator metrics."""

    def __init__(
        self,
        settings: Any,
        hybrid_search: Any,
        evaluator: BaseEvaluator,
        top_k: int | None = None,
    ) -> None:
        self.settings = settings
        self.hybrid_search = hybrid_search
        self.evaluator = evaluator
        self.top_k = top_k

    def run(self, test_set_path: str | Path) -> EvalReport:
        """Run evaluation for all cases in a golden test set."""
        cases = load_golden_test_set(test_set_path)
        case_results = [self._run_case(case) for case in cases]
        return EvalReport(
            metrics=_aggregate_metrics(case_results),
            case_results=case_results,
            details={
                "test_set_path": str(test_set_path),
                "case_count": len(case_results),
            },
        )

    def _run_case(self, case: EvalCase) -> EvalCaseResult:
        top_k = case.top_k or self.top_k or _default_top_k(self.settings)
        retrieved = self.hybrid_search.search(
            case.query,
            top_k=top_k,
            filters=case.filters or None,
        )
        retrieved_ids = [_retrieval_id(result) for result in retrieved]
        evaluation = self.evaluator.evaluate(
            query=case.query,
            retrieved_ids=retrieved_ids,
            golden_ids=case.expected_chunk_ids,
            generated_answer=case.generated_answer,
        )
        return EvalCaseResult(
            query=case.query,
            retrieved_ids=retrieved_ids,
            expected_chunk_ids=list(case.expected_chunk_ids),
            metrics=dict(evaluation.metrics),
            details={
                **dict(evaluation.details),
                "expected_sources": list(case.expected_sources),
                "top_k": top_k,
            },
        )


def load_golden_test_set(path: str | Path) -> list[EvalCase]:
    """Load and validate golden cases from JSON."""
    test_set_path = Path(path)
    if not test_set_path.is_file():
        raise EvalRunnerError(f"golden test set not found: {test_set_path}")
    with test_set_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict) or not isinstance(payload.get("test_cases"), list):
        raise EvalRunnerError("golden test set must contain a test_cases list")
    cases = [_parse_case(item, index) for index, item in enumerate(payload["test_cases"])]
    if not cases:
        raise EvalRunnerError("golden test set must contain at least one test case")
    return cases


def _parse_case(payload: Any, index: int) -> EvalCase:
    if not isinstance(payload, dict):
        raise EvalRunnerError(f"test case #{index + 1} must be a mapping")
    query = payload.get("query")
    expected_chunk_ids = payload.get("expected_chunk_ids")
    expected_sources = payload.get("expected_sources", [])
    filters = payload.get("filters", {})
    if not isinstance(query, str) or not query.strip():
        raise EvalRunnerError(f"test case #{index + 1} query must be a non-empty string")
    if not isinstance(expected_chunk_ids, list) or not all(
        isinstance(item, str) and item for item in expected_chunk_ids
    ):
        raise EvalRunnerError(
            f"test case #{index + 1} expected_chunk_ids must be a non-empty string list"
        )
    if not expected_chunk_ids:
        raise EvalRunnerError(
            f"test case #{index + 1} expected_chunk_ids must not be empty"
        )
    if not isinstance(expected_sources, list) or not all(
        isinstance(item, str) for item in expected_sources
    ):
        raise EvalRunnerError(
            f"test case #{index + 1} expected_sources must be a string list"
        )
    if not isinstance(filters, dict):
        raise EvalRunnerError(f"test case #{index + 1} filters must be a mapping")
    return EvalCase(
        query=query,
        expected_chunk_ids=list(expected_chunk_ids),
        expected_sources=list(expected_sources),
        generated_answer=str(payload.get("generated_answer", "")),
        top_k=payload.get("top_k"),
        filters=dict(filters),
    )


def _retrieval_id(result: RetrievalResult | Any) -> str:
    chunk_id = getattr(result, "chunk_id", None)
    if chunk_id is None and isinstance(result, dict):
        chunk_id = result.get("chunk_id") or result.get("id")
    if not isinstance(chunk_id, str) or not chunk_id:
        raise EvalRunnerError("retrieval result must contain a non-empty chunk_id")
    return chunk_id


def _aggregate_metrics(case_results: list[EvalCaseResult]) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for result in case_results:
        for key, value in result.metrics.items():
            grouped.setdefault(key, []).append(float(value))
    return {key: fmean(values) for key, values in sorted(grouped.items())}


def _default_top_k(settings: Any) -> int:
    retrieval = getattr(settings, "retrieval", None)
    value = int(getattr(retrieval, "fusion_top_k", 10))
    return value if value > 0 else 10
