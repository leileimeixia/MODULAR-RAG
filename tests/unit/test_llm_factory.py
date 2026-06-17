"""Tests for the pluggable LLM factory."""

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
from libs.llm import BaseLLM, LLMFactory, LLMFactoryError


class FakeLLM(BaseLLM):
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings

    def chat(self, messages: list[dict[str, str]]) -> str:
        return messages[-1]["content"] if messages else ""


@pytest.fixture(autouse=True)
def clean_registry():
    LLMFactory.unregister("fake")
    yield
    LLMFactory.unregister("fake")


def _settings(provider: str = "fake") -> Settings:
    return Settings(
        llm=LLMSettings(provider=provider, model="fake-model", api_key="key"),
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
    )


def test_factory_creates_registered_provider_from_full_settings() -> None:
    LLMFactory.register("fake", FakeLLM)

    llm = LLMFactory.create(_settings())

    assert isinstance(llm, FakeLLM)
    assert llm.settings.model == "fake-model"
    assert llm.chat([{"role": "user", "content": "hello"}]) == "hello"


def test_factory_creates_registered_provider_from_llm_settings() -> None:
    LLMFactory.register("fake", FakeLLM)

    llm = LLMFactory.create(LLMSettings(provider="fake", model="model"))

    assert isinstance(llm, FakeLLM)
    assert llm.settings.provider == "fake"


def test_factory_normalizes_provider_names() -> None:
    LLMFactory.register("fake-provider", FakeLLM)

    llm = LLMFactory.create(LLMSettings(provider=" FAKE_PROVIDER ", model="model"))

    assert isinstance(llm, FakeLLM)
    LLMFactory.unregister("fake-provider")


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(LLMFactoryError, match="Unsupported LLM provider 'missing'"):
        LLMFactory.create(_settings(provider="missing"))


def test_base_llm_requires_chat_implementation() -> None:
    with pytest.raises(TypeError):
        BaseLLM()
