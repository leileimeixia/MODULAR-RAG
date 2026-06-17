"""Tests for the pluggable splitter factory."""

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
from libs.splitter import BaseSplitter, SplitterFactory, SplitterFactoryError


class FakeSplitter(BaseSplitter):
    def __init__(self, settings: SplitterSettings) -> None:
        self.settings = settings

    def split_text(self, text: str, trace=None) -> list[str]:
        return [part.strip() for part in text.split("|") if part.strip()]


@pytest.fixture(autouse=True)
def clean_registry():
    SplitterFactory.unregister("fake")
    yield
    SplitterFactory.unregister("fake")


def _settings(provider: str = "fake") -> Settings:
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
        rerank=RerankSettings(enabled=False, provider="none"),
        evaluation=EvaluationSettings(enabled=False, provider="custom"),
        observability=ObservabilitySettings(
            log_level="INFO",
            trace_enabled=True,
            trace_file="./logs/traces.jsonl",
        ),
        splitter=SplitterSettings(provider=provider, chunk_size=100, chunk_overlap=10),
    )


def test_factory_creates_registered_provider_from_full_settings() -> None:
    SplitterFactory.register("fake", FakeSplitter)

    splitter = SplitterFactory.create(_settings())

    assert isinstance(splitter, FakeSplitter)
    assert splitter.settings.chunk_size == 100
    assert splitter.split_text("one | two") == ["one", "two"]


def test_factory_creates_registered_provider_from_splitter_settings() -> None:
    SplitterFactory.register("fake", FakeSplitter)

    splitter = SplitterFactory.create(
        SplitterSettings(provider="fake", chunk_size=50, chunk_overlap=5)
    )

    assert isinstance(splitter, FakeSplitter)
    assert splitter.settings.chunk_overlap == 5


def test_factory_normalizes_provider_names() -> None:
    SplitterFactory.register("fake-provider", FakeSplitter)

    splitter = SplitterFactory.create(SplitterSettings(provider=" FAKE_PROVIDER "))

    assert isinstance(splitter, FakeSplitter)
    SplitterFactory.unregister("fake-provider")


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(
        SplitterFactoryError,
        match="Unsupported splitter provider 'missing'",
    ):
        SplitterFactory.create(_settings(provider="missing"))


def test_base_splitter_requires_split_text_implementation() -> None:
    with pytest.raises(TypeError):
        BaseSplitter()
