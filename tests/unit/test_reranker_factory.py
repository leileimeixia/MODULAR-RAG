"""Tests for the pluggable reranker factory."""

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
    VectorStoreSettings,
    VisionLLMSettings,
)
from libs.reranker import (
    BaseReranker,
    NoneReranker,
    RerankCandidate,
    RerankResult,
    RerankerFactory,
    RerankerFactoryError,
)


class FakeReranker(BaseReranker):
    def __init__(self, settings: RerankSettings) -> None:
        self.settings = settings

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        top_k: int | None = None,
        trace=None,
    ) -> list[RerankResult]:
        limit = top_k if top_k is not None else self.settings.top_k
        ranked = sorted(candidates, key=lambda item: item.text.count(query), reverse=True)
        return [
            RerankResult(
                id=candidate.id,
                text=candidate.text,
                score=float(candidate.text.count(query)),
                metadata=candidate.metadata,
            )
            for candidate in ranked[:limit]
        ]


@pytest.fixture(autouse=True)
def clean_registry():
    RerankerFactory.unregister("fake")
    yield
    RerankerFactory.unregister("fake")


def _settings(
    provider: str = "fake",
    enabled: bool = True,
    top_k: int = 2,
) -> Settings:
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
        rerank=RerankSettings(
            enabled=enabled,
            provider=provider,
            model="fake-reranker",
            top_k=top_k,
        ),
        evaluation=EvaluationSettings(enabled=False, provider="custom"),
        observability=ObservabilitySettings(
            log_level="INFO",
            trace_enabled=True,
            trace_file="./logs/traces.jsonl",
        ),
    )


def test_factory_creates_registered_provider_from_full_settings() -> None:
    RerankerFactory.register("fake", FakeReranker)

    reranker = RerankerFactory.create(_settings())

    assert isinstance(reranker, FakeReranker)
    assert reranker.settings.model == "fake-reranker"
    assert reranker.rerank(
        "rag",
        [
            RerankCandidate(id="a", text="rag rag", score=0.2),
            RerankCandidate(id="b", text="rag", score=0.9),
        ],
    ) == [
        RerankResult(id="a", text="rag rag", score=2.0),
        RerankResult(id="b", text="rag", score=1.0),
    ]


def test_factory_creates_registered_provider_from_rerank_settings() -> None:
    RerankerFactory.register("fake", FakeReranker)

    reranker = RerankerFactory.create(
        RerankSettings(enabled=True, provider="fake", model="model", top_k=1)
    )

    assert isinstance(reranker, FakeReranker)
    assert reranker.settings.top_k == 1


def test_factory_returns_none_reranker_when_disabled() -> None:
    reranker = RerankerFactory.create(_settings(provider="missing", enabled=False))

    assert isinstance(reranker, NoneReranker)
    assert reranker.rerank(
        "query",
        [
            RerankCandidate(id="a", text="first", score=0.3),
            RerankCandidate(id="b", text="second", score=0.2),
        ],
        top_k=1,
    ) == [RerankResult(id="a", text="first", score=0.3)]


def test_factory_normalizes_provider_names() -> None:
    RerankerFactory.register("fake-provider", FakeReranker)

    reranker = RerankerFactory.create(
        RerankSettings(enabled=True, provider=" FAKE_PROVIDER ", model="model")
    )

    assert isinstance(reranker, FakeReranker)
    RerankerFactory.unregister("fake-provider")


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(
        RerankerFactoryError,
        match="Unsupported reranker provider 'missing'",
    ):
        RerankerFactory.create(_settings(provider="missing"))


def test_base_reranker_requires_rerank_implementation() -> None:
    with pytest.raises(TypeError):
        BaseReranker()
