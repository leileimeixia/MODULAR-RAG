"""Tests for the pluggable embedding factory."""

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
from libs.embedding import BaseEmbedding, EmbeddingFactory, EmbeddingFactoryError


class FakeEmbedding(BaseEmbedding):
    def __init__(self, settings: EmbeddingSettings) -> None:
        self.settings = settings

    def embed(self, texts: list[str], trace=None) -> list[list[float]]:
        return [[float(len(text)), float(index)] for index, text in enumerate(texts)]


@pytest.fixture(autouse=True)
def clean_registry():
    EmbeddingFactory.unregister("fake")
    yield
    EmbeddingFactory.unregister("fake")


def _settings(provider: str = "fake") -> Settings:
    return Settings(
        llm=LLMSettings(provider="openai", model="gpt-5.5"),
        embedding=EmbeddingSettings(
            provider=provider,
            model="fake-embedding",
            dimensions=2,
            api_key="key",
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
        rerank=RerankSettings(enabled=False, provider="none"),
        evaluation=EvaluationSettings(enabled=False, provider="custom"),
        observability=ObservabilitySettings(
            log_level="INFO",
            trace_enabled=True,
            trace_file="./logs/traces.jsonl",
        ),
    )


def test_factory_creates_registered_provider_from_full_settings() -> None:
    EmbeddingFactory.register("fake", FakeEmbedding)

    embedding = EmbeddingFactory.create(_settings())

    assert isinstance(embedding, FakeEmbedding)
    assert embedding.settings.model == "fake-embedding"
    assert embedding.embed(["a", "abcd"]) == [[1.0, 0.0], [4.0, 1.0]]


def test_factory_creates_registered_provider_from_embedding_settings() -> None:
    EmbeddingFactory.register("fake", FakeEmbedding)

    embedding = EmbeddingFactory.create(
        EmbeddingSettings(provider="fake", model="model", dimensions=2)
    )

    assert isinstance(embedding, FakeEmbedding)
    assert embedding.settings.dimensions == 2


def test_factory_normalizes_provider_names() -> None:
    EmbeddingFactory.register("fake-provider", FakeEmbedding)

    embedding = EmbeddingFactory.create(
        EmbeddingSettings(provider=" FAKE_PROVIDER ", model="model", dimensions=2)
    )

    assert isinstance(embedding, FakeEmbedding)
    EmbeddingFactory.unregister("fake-provider")


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(
        EmbeddingFactoryError,
        match="Unsupported embedding provider 'missing'",
    ):
        EmbeddingFactory.create(_settings(provider="missing"))


def test_base_embedding_requires_embed_implementation() -> None:
    with pytest.raises(TypeError):
        BaseEmbedding()
