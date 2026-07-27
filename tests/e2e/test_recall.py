"""Recall regression tests built from the golden test set."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core import RetrievalResult
from libs.evaluator import CustomEvaluator
from observability.evaluation import EvalRunner


GOLDEN_TEST_SET = Path("tests/fixtures/golden_test_set.json")
MIN_HIT_RATE = 1.0
MIN_MRR = 0.75


@dataclass(frozen=True)
class FakeRetrievalSettings:
    fusion_top_k: int = 3


@dataclass(frozen=True)
class FakeSettings:
    retrieval: FakeRetrievalSettings = FakeRetrievalSettings()


class GoldenHybridSearch:
    """Deterministic retrieval route for recall regression tests."""

    def search(self, query: str, top_k: int, filters=None):
        results = {
            "How do I configure Azure OpenAI?": [
                _result("chunk_azure_openai_001", 0.95),
                _result("chunk_general_config_001", 0.4),
            ],
            "How can I inspect ingestion progress?": [
                _result("chunk_dashboard_overview_001", 0.8),
                _result("chunk_dashboard_ingestion_001", 0.75),
            ],
        }.get(query, [])
        return results[:top_k]


def test_golden_set_recall_thresholds_hold() -> None:
    report = EvalRunner(
        settings=FakeSettings(),
        hybrid_search=GoldenHybridSearch(),
        evaluator=CustomEvaluator(),
    ).run(GOLDEN_TEST_SET)

    assert report.details["case_count"] >= 2
    assert report.metrics["hit_rate"] >= MIN_HIT_RATE
    assert report.metrics["mrr"] >= MIN_MRR
    assert all(
        set(result.expected_chunk_ids).intersection(result.retrieved_ids)
        for result in report.case_results
    )


def _result(chunk_id: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        score=score,
        text=f"content for {chunk_id}",
        metadata={"source_path": f"docs/{chunk_id}.md"},
    )
