"""Tests for custom evaluator metrics and factory routing."""

from __future__ import annotations

import pytest

from core.settings import (
    EmbeddingSettings,
    EvaluationSettings,
    LLMSettings,
    ObservabilitySettings,
    RerankSettings,
    RetrievalSettings,
    Settings,
    SplitterSettings,
    VectorStoreSettings,
    VisionLLMSettings,
)
from libs.evaluator import (
    BaseEvaluator,
    CustomEvaluator,
    EvaluationResult,
    EvaluatorFactory,
    EvaluatorFactoryError,
)


class FakeEvaluator(BaseEvaluator):
    def __init__(self, settings: EvaluationSettings) -> None:
        self.settings = settings

    def evaluate(
        self,
        query: str,
        retrieved_ids: list[str],
        golden_ids: list[str],
        generated_answer: str = "",
        trace=None,
    ) -> EvaluationResult:
        return EvaluationResult(metrics={"fake": 1.0}, details={"query": query})


@pytest.fixture(autouse=True)
def clean_registry():
    EvaluatorFactory.unregister("fake")
    yield
    EvaluatorFactory.unregister("fake")


def _settings(provider: str = "custom", enabled: bool = True) -> Settings:
    return Settings(
        llm=LLMSettings(provider="openai", model="gpt-5.5"),
        embedding=EmbeddingSettings(
            provider="openai",
            model="text-embedding-ada-002",
            dimensions=1536,
        ),
        vision_llm=VisionLLMSettings(
            enabled=False,
            provider="openai",
            model="gpt-4o",
        ),
        vector_store=VectorStoreSettings(
            provider="chroma",
            persist_directory="./data/db/chroma",
            collection_name="knowledge_hub",
        ),
        retrieval=RetrievalSettings(
            dense_top_k=20,
            sparse_top_k=20,
            fusion_top_k=10,
            rrf_k=60,
        ),
        splitter=SplitterSettings(provider="recursive"),
        rerank=RerankSettings(enabled=False, provider="none"),
        evaluation=EvaluationSettings(enabled=enabled, provider=provider),
        observability=ObservabilitySettings(
            log_level="INFO",
            trace_enabled=True,
            trace_file="./logs/traces.jsonl",
        ),
    )


def test_custom_evaluator_returns_stable_retrieval_metrics() -> None:
    evaluator = CustomEvaluator(EvaluationSettings(enabled=True, provider="custom"))

    result = evaluator.evaluate(
        query="rag",
        retrieved_ids=["chunk-a", "chunk-b", "chunk-c"],
        golden_ids=["chunk-b", "chunk-x"],
    )

    assert result.metrics == {
        "hit_rate": 1.0,
        "mrr": 0.5,
        "precision": pytest.approx(1 / 3),
    }
    assert result.details["first_hit_rank"] == 2


def test_custom_evaluator_handles_empty_inputs() -> None:
    evaluator = CustomEvaluator()

    result = evaluator.evaluate(query="rag", retrieved_ids=[], golden_ids=["chunk-a"])

    assert result.metrics == {
        "hit_rate": 0.0,
        "mrr": 0.0,
        "precision": 0.0,
    }
    assert result.details["first_hit_rank"] is None


def test_custom_evaluator_handles_empty_golden_ids() -> None:
    evaluator = CustomEvaluator()

    result = evaluator.evaluate(query="rag", retrieved_ids=["chunk-a"], golden_ids=[])

    assert result.metrics == {
        "hit_rate": 0.0,
        "mrr": 0.0,
        "precision": 0.0,
    }
    assert result.details == {
        "query": "rag",
        "retrieved_count": 1,
        "golden_count": 0,
        "first_hit_rank": None,
    }


def test_custom_evaluator_uses_unique_golden_ids_but_counts_retrieved_hits() -> None:
    evaluator = CustomEvaluator()

    result = evaluator.evaluate(
        query="rag",
        retrieved_ids=["chunk-a", "chunk-a", "chunk-b"],
        golden_ids=["chunk-a", "chunk-a"],
    )

    assert result.metrics == {
        "hit_rate": 1.0,
        "mrr": 1.0,
        "precision": pytest.approx(2 / 3),
    }
    assert result.details["golden_count"] == 1


def test_factory_creates_default_custom_evaluator_from_full_settings() -> None:
    evaluator = EvaluatorFactory.create(_settings())

    assert isinstance(evaluator, CustomEvaluator)
    assert evaluator.settings == EvaluationSettings(enabled=True, provider="custom")


def test_factory_creates_registered_provider_from_evaluation_settings() -> None:
    EvaluatorFactory.register("fake", FakeEvaluator)

    evaluator = EvaluatorFactory.create(EvaluationSettings(enabled=True, provider="fake"))

    assert isinstance(evaluator, FakeEvaluator)
    assert evaluator.evaluate("q", [], []).metrics == {"fake": 1.0}


def test_factory_normalizes_provider_names() -> None:
    EvaluatorFactory.register("fake-provider", FakeEvaluator)

    evaluator = EvaluatorFactory.create(
        EvaluationSettings(enabled=True, provider=" FAKE_PROVIDER ")
    )

    assert isinstance(evaluator, FakeEvaluator)
    EvaluatorFactory.unregister("fake-provider")


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(
        EvaluatorFactoryError,
        match="Unsupported evaluator provider 'missing'",
    ):
        EvaluatorFactory.create(_settings(provider="missing"))


def test_factory_rejects_empty_provider() -> None:
    with pytest.raises(
        EvaluatorFactoryError,
        match="provider must be a non-empty string",
    ):
        EvaluatorFactory.create(_settings(provider=" "))


def test_base_evaluator_requires_evaluate_implementation() -> None:
    with pytest.raises(TypeError):
        BaseEvaluator()
